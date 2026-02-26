"""Memory API — 记忆系统管理端点。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/memory", tags=["memory"])


class AddMemoryRequest(BaseModel):
    collection: str = "lessons"
    content: str
    metadata: dict | None = None


class SearchMemoryRequest(BaseModel):
    query: str
    collection: str | None = None
    limit: int = 6


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    metadata: dict | None = None


def _get_store():
    """获取全局 MemoryStore 实例。"""
    try:
        from memory.config import load_config
        from memory.store import MemoryStore
        from pathlib import Path
        cfg = load_config()
        db_path = Path(__file__).parent.parent / "data" / "memory" / "main.sqlite"
        return MemoryStore(db_path, cfg.embedding_dim)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MemoryStore 初始化失败: {e}")


@router.get("/config")
async def get_memory_config():
    """获取记忆系统配置。"""
    from memory.config import load_config
    return load_config().to_dict()


@router.post("/config")
async def update_memory_config(updates: dict):
    """更新记忆系统配置。"""
    from memory.config import load_config, save_config
    from memory.types import MemoryConfig
    cfg = load_config()
    merged = {**cfg.to_dict(), **updates}
    new_cfg = MemoryConfig.from_dict(merged)
    save_config(new_cfg)
    return new_cfg.to_dict()


@router.get("/stats")
async def get_memory_stats():
    """获取记忆统计信息。"""
    store = _get_store()
    try:
        collections = store.list_collections()
        total = store.count()
        return {"total": total, "collections": collections}
    finally:
        store.close()


@router.post("/add")
async def add_memory(req: AddMemoryRequest):
    """添加一条记忆。"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    store = _get_store()
    try:
        mem_id = store.add(
            collection=req.collection,
            content=req.content,
            metadata=req.metadata,
        )
        return {"id": mem_id, "collection": req.collection}
    finally:
        store.close()


@router.post("/search")
async def search_memory(req: SearchMemoryRequest):
    """搜索记忆。"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    store = _get_store()
    try:
        from memory.config import load_config
        cfg = load_config()
        results = store.search_hybrid(
            query_text=req.query,
            collection=req.collection,
            vector_weight=cfg.vector_weight,
            text_weight=cfg.text_weight,
            limit=req.limit,
            min_score=cfg.min_score,
        )
        return {"results": [r.to_dict() for r in results], "count": len(results)}
    finally:
        store.close()


@router.get("/list")
async def list_memories(collection: str | None = None, limit: int = 50, offset: int = 0):
    """列出记忆（分页）。"""
    store = _get_store()
    try:
        results = store.get_all(collection=collection, limit=limit, offset=offset)
        return {"results": [r.to_dict() for r in results], "count": len(results)}
    finally:
        store.close()


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """删除一条记忆。"""
    store = _get_store()
    try:
        ok = store.delete(memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"记忆不存在: {memory_id}")
        return {"deleted": memory_id}
    finally:
        store.close()


@router.put("/{memory_id}")
async def update_memory(memory_id: str, req: UpdateMemoryRequest):
    """更新一条记忆。"""
    store = _get_store()
    try:
        ok = store.update(memory_id, content=req.content, metadata=req.metadata)
        if not ok:
            raise HTTPException(status_code=404, detail=f"记忆不存在: {memory_id}")
        return {"updated": memory_id}
    finally:
        store.close()


@router.post("/migrate")
async def migrate_from_lessons():
    """从 lessons.json 迁移到 MemoryStore。"""
    store = _get_store()
    try:
        from memory.migrate import migrate_lessons_to_store
        result = migrate_lessons_to_store(store)
        return result
    finally:
        store.close()
