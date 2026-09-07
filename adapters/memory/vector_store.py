"""S39: 向量语义检索 — 轻量级本地向量存储。

在现有 BM25 + 时间衰减基础上增加语义向量检索层。
使用 sentence-transformers 生成嵌入，numpy 做余弦相似度。
降级方案: 无模型时自动回退到 BM25。

不修改 retrieval.py（规则 06），作为增强层叠加。
"""
import json
import hashlib
import sqlite3
import struct
import numpy as np
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("vector")

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_CACHE_PATH = _DATA_DIR / "embeddings_cache.json"
_CACHE_DB_PATH = _DATA_DIR / "embeddings_cache.db"
_CACHE_MAX_ENTRIES = 10000


class VectorStore:
    """轻量级向量存储 — 本地嵌入 + 余弦相似度。"""

    def __init__(self):
        self._model = None
        self._model_loaded = False
        self._loading = False
        self._cache_db: sqlite3.Connection | None = None
        self._mem_cache: dict[str, list[float]] = {}
        self._init_cache_db()

    def _init_cache_db(self):
        """初始化 SQLite 向量缓存（替代 JSON，上限 10,000 条）。"""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._cache_db = sqlite3.connect(str(_CACHE_DB_PATH))
            self._cache_db.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    hash TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    dims INTEGER NOT NULL,
                    accessed_at REAL NOT NULL
                )
            """)
            self._cache_db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_accessed ON embedding_cache(accessed_at)")
            self._cache_db.commit()
            count = self._cache_db.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
            logger.info(f"向量缓存(SQLite)已加载: {count} 条 (上限 {_CACHE_MAX_ENTRIES})")
            # 自动迁移旧 JSON 缓存
            if count == 0:
                self._migrate_json_cache()
        except Exception as e:
            logger.warning(f"SQLite 缓存初始化失败，降级到内存缓存: {e}")
            self._cache_db = None

    def _migrate_json_cache(self):
        """将旧 JSON 缓存迁移到 SQLite。"""
        if not _CACHE_PATH.exists():
            return
        try:
            old_cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if not isinstance(old_cache, dict) or not old_cache:
                return
            import time
            now = time.time()
            batch = []
            for h, vec in old_cache.items():
                if not isinstance(vec, list) or not vec:
                    continue
                blob = struct.pack(f"{len(vec)}f", *vec)
                batch.append((h, blob, len(vec), now))
            if batch and self._cache_db:
                self._cache_db.executemany(
                    "INSERT OR IGNORE INTO embedding_cache (hash, embedding, dims, accessed_at) VALUES (?,?,?,?)",
                    batch)
                self._cache_db.commit()
                logger.info(f"JSON→SQLite 缓存迁移完成: {len(batch)} 条")
                # 迁移成功后重命名旧文件
                _CACHE_PATH.rename(_CACHE_PATH.with_suffix(".json.bak"))
        except Exception as e:
            logger.warning(f"JSON 缓存迁移失败(不影响使用): {e}")

    def _cache_get(self, h: str) -> list[float] | None:
        """从缓存获取向量（SQLite → 内存 fallback）。"""
        # 内存热缓存
        if h in self._mem_cache:
            return self._mem_cache[h]
        if not self._cache_db:
            return None
        try:
            import time
            row = self._cache_db.execute(
                "SELECT embedding, dims FROM embedding_cache WHERE hash=?", (h,)
            ).fetchone()
            if row:
                blob, dims = row
                vec = list(struct.unpack(f"{dims}f", blob))
                self._cache_db.execute(
                    "UPDATE embedding_cache SET accessed_at=? WHERE hash=?",
                    (time.time(), h))
                self._mem_cache[h] = vec
                return vec
        except Exception:
            pass
        return None

    def _cache_put(self, h: str, vec: list[float]):
        """写入缓存（SQLite + 内存热缓存）。"""
        self._mem_cache[h] = vec
        if not self._cache_db:
            return
        try:
            import time
            blob = struct.pack(f"{len(vec)}f", *vec)
            self._cache_db.execute(
                "INSERT OR REPLACE INTO embedding_cache (hash, embedding, dims, accessed_at) VALUES (?,?,?,?)",
                (h, blob, len(vec), time.time()))
            if hash(h) % 50 == 0:  # 每约50次写入 commit + LRU 清理
                self._cache_db.commit()
                self._prune_cache()
        except Exception as e:
            logger.debug(f"缓存写入异常: {e}")

    def _prune_cache(self):
        """LRU 淘汰: 超过上限时删除最久未访问的条目。"""
        if not self._cache_db:
            return
        try:
            count = self._cache_db.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
            if count > _CACHE_MAX_ENTRIES:
                excess = count - int(_CACHE_MAX_ENTRIES * 0.8)
                self._cache_db.execute(
                    "DELETE FROM embedding_cache WHERE hash IN "
                    "(SELECT hash FROM embedding_cache ORDER BY accessed_at ASC LIMIT ?)",
                    (excess,))
                self._cache_db.commit()
                logger.info(f"向量缓存 LRU 淘汰: {count}→{count - excess} 条")
        except Exception as e:
            logger.debug(f"缓存淘汰异常: {e}")

    def _ensure_model(self):
        if self._model_loaded:
            return self._model is not None
        if self._loading:
            return False
        self._loading = True
        self._model_loaded = True
        # 按优先级尝试: Ollama → OpenAI → sentence-transformers
        if self._try_ollama():
            self._loading = False
            return True
        if self._try_openai():
            self._loading = False
            return True
        # sentence-transformers (后台线程加载，不阻塞对话)
        import threading
        def _bg_load():
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                self._model_loaded = True
                self._provider = "sentence-transformers"
                logger.info("向量模型: sentence-transformers (后台加载完成)")
            except Exception as e:
                logger.info(f"向量检索降级到 BM25（{e}）")
            self._loading = False
        threading.Thread(target=_bg_load, daemon=True).start()
        logger.info("向量模型后台加载中，暂时降级到 BM25")
        return False

    def _try_ollama(self) -> bool:
        """尝试 Ollama 嵌入模型。"""
        try:
            import requests
            for m in ("nomic-embed-text", "all-minilm"):
                try:
                    r = requests.post("http://localhost:11434/api/embeddings",
                                      json={"model": m, "prompt": "test"}, timeout=15)
                    if r.status_code == 200 and r.json().get("embedding"):
                        self._model = "ollama"
                        self._provider = "ollama"
                        self._ollama_model = m
                        self._embed_dim = len(r.json()["embedding"])
                        logger.info(f"向量模型: Ollama {m} (dim={self._embed_dim})")
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _try_openai(self) -> bool:
        """尝试 OpenAI Embeddings API（需 OPENAI_API_KEY 环境变量）。"""
        import os
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return False
        try:
            import requests
            model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            r = requests.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": "test"},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json().get("data", [{}])
                if data and data[0].get("embedding"):
                    self._model = "openai"
                    self._provider = "openai"
                    self._openai_model = model
                    self._openai_key = api_key
                    self._openai_base = base_url
                    self._embed_dim = len(data[0]["embedding"])
                    logger.info(f"向量模型: OpenAI {model} (dim={self._embed_dim})")
                    return True
        except Exception as e:
            logger.debug(f"OpenAI embedding 探测失败: {e}")
        return False

    def _text_hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    def embed(self, text: str) -> list[float] | None:
        """生成文本嵌入向量（带 SQLite 缓存，上限 10,000 条）。

        支持三种 provider: ollama / openai / sentence-transformers
        """
        if not self._ensure_model():
            return None
        h = self._text_hash(text)
        cached = self._cache_get(h)
        if cached is not None:
            return cached
        try:
            if self._model == "ollama":
                import requests
                r = requests.post("http://localhost:11434/api/embeddings",
                                  json={"model": getattr(self, '_ollama_model', 'nomic-embed-text'), "prompt": text[:512]}, timeout=15)
                vec = r.json().get("embedding")
            elif self._model == "openai":
                import requests
                r = requests.post(
                    f"{self._openai_base}/embeddings",
                    headers={"Authorization": f"Bearer {self._openai_key}"},
                    json={"model": self._openai_model, "input": text[:8000]},
                    timeout=30,
                )
                data = r.json().get("data", [{}])
                vec = data[0].get("embedding") if data else None
            else:
                vec = self._model.encode(text[:512], normalize_embeddings=True).tolist()
            if vec:
                self._cache_put(h, vec)
            return vec
        except Exception as e:
            logger.warning(f"嵌入生成失败: {e}")
            return None

    def get_provider(self) -> str:
        """返回当前 embedding provider 名称。"""
        return getattr(self, '_provider', 'none')

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度。"""
        va, vb = np.array(a), np.array(b)
        dot = np.dot(va, vb)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na == 0 or nb == 0:
            return 0.0
        return float(dot / (na * nb))

    def semantic_search(self, query: str, items: list[dict], text_fields: list[str],
                        limit: int = 5) -> list[dict]:
        """语义向量检索。"""
        query_vec = self.embed(query)
        if query_vec is None:
            return []  # 降级：调用方会 fallback 到 BM25

        scored = []
        for item in items:
            doc_text = " ".join(str(item.get(f, "")) for f in text_fields)[:512]
            doc_vec = self.embed(doc_text)
            if doc_vec is None:
                continue
            sim = self.cosine_similarity(query_vec, doc_vec)
            if sim > 0.3:  # 相似度阈值
                scored.append({**item, "_vec_score": sim})

        scored.sort(key=lambda x: x["_vec_score"], reverse=True)
        return scored[:limit]

    def is_available(self) -> bool:
        return self._ensure_model()


# 全局单例
_store: VectorStore | None = None

def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
