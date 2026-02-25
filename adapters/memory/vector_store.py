"""S39: 向量语义检索 — 轻量级本地向量存储。

在现有 BM25 + 时间衰减基础上增加语义向量检索层。
使用 sentence-transformers 生成嵌入，numpy 做余弦相似度。
降级方案: 无模型时自动回退到 BM25。

不修改 retrieval.py（规则 06），作为增强层叠加。
"""
import json
import hashlib
import numpy as np
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("vector")

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_CACHE_PATH = _DATA_DIR / "embeddings_cache.json"


class VectorStore:
    """轻量级向量存储 — 本地嵌入 + 余弦相似度。"""

    def __init__(self):
        self._model = None
        self._model_loaded = False
        self._loading = False
        self._cache: dict[str, list[float]] = {}
        self._load_cache()

    def _load_cache(self):
        try:
            if _CACHE_PATH.exists():
                self._cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                logger.info(f"向量缓存已加载: {len(self._cache)} 条")
        except Exception:
            self._cache = {}

    def _save_cache(self):
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            # 只保留最近1000条缓存
            if len(self._cache) > 1000:
                keys = list(self._cache.keys())[-800:]
                self._cache = {k: self._cache[k] for k in keys}
            _CACHE_PATH.write_text(json.dumps(self._cache), encoding="utf-8")
        except Exception as e:
            logger.warning(f"向量缓存保存失败: {e}")

    def _ensure_model(self):
        if self._model_loaded:
            return self._model is not None
        if self._loading:
            return False
        self._loading = True
        self._model_loaded = True
        # 方案1: Ollama 专用嵌入模型 (需先 ollama pull nomic-embed-text)
        try:
            import requests
            for m in ("nomic-embed-text", "all-minilm"):
                try:
                    r = requests.post("http://localhost:11434/api/embeddings",
                                      json={"model": m, "prompt": "test"}, timeout=15)
                    if r.status_code == 200 and r.json().get("embedding"):
                        self._model = "ollama"
                        self._ollama_model = m
                        self._embed_dim = len(r.json()["embedding"])
                        logger.info(f"向量模型: Ollama {m} (dim={self._embed_dim})")
                        self._loading = False
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        # 方案2: sentence-transformers (后台线程加载，不阻塞对话)
        import threading
        def _bg_load():
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                self._model_loaded = True
                logger.info("向量模型: sentence-transformers (后台加载完成)")
            except Exception as e:
                logger.info(f"向量检索降级到 BM25（{e}）")
            self._loading = False
        threading.Thread(target=_bg_load, daemon=True).start()
        logger.info("向量模型后台加载中，暂时降级到 BM25")
        return False

    def _text_hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    def embed(self, text: str) -> list[float] | None:
        """生成文本嵌入向量（带缓存）。"""
        if not self._ensure_model():
            return None
        h = self._text_hash(text)
        if h in self._cache:
            return self._cache[h]
        try:
            if self._model == "ollama":
                import requests
                r = requests.post("http://localhost:11434/api/embeddings",
                                  json={"model": getattr(self, '_ollama_model', 'nomic-embed-text'), "prompt": text[:512]}, timeout=15)
                vec = r.json().get("embedding")
            else:
                vec = self._model.encode(text[:512], normalize_embeddings=True).tolist()
            if vec:
                self._cache[h] = vec
                if len(self._cache) % 50 == 0:
                    self._save_cache()
            return vec
        except Exception as e:
            logger.warning(f"嵌入生成失败: {e}")
            return None

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
