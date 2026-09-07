"""S18: 多会话管理 API。"""
import json
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from logs import get_logger

logger = get_logger("sessions")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

DATA_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
META_FILE = DATA_DIR / "sessions_meta.json"

# 会话 ID 白名单：仅允许字母/数字/下划线/连字符，防止路径遍历
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_session_id(session_id: str) -> str:
    """校验会话 ID，非法（含 ../ 等路径遍历字符）时返回 400。"""
    if not _SESSION_ID_RE.match(session_id or ""):
        raise HTTPException(400, "非法的会话 ID")
    return session_id


def _load_meta() -> list[dict]:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_meta(meta: list[dict]):
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_default():
    """确保至少有一个 default 会话。"""
    meta = _load_meta()
    if not any(s["id"] == "default" for s in meta):
        meta.insert(0, {"id": "default", "title": "默认对话", "created": time.time(), "updated": time.time()})
        _save_meta(meta)
    return meta


class CreateSessionRequest(BaseModel):
    title: str | None = None


@router.get("")
async def list_sessions():
    """列出所有会话。"""
    meta = _ensure_default()
    # 按更新时间倒序
    meta.sort(key=lambda s: s.get("updated", 0), reverse=True)
    # 附加消息数
    for s in meta:
        f = SESSIONS_DIR / f"{s['id']}.json"
        try:
            msgs = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
            s["message_count"] = len(msgs)
        except Exception:
            s["message_count"] = 0
    return {"sessions": meta}


@router.post("")
async def create_session(req: CreateSessionRequest):
    """创建新会话。"""
    meta = _ensure_default()
    sid = f"s_{uuid.uuid4().hex[:8]}"
    title = req.title or f"对话 {len(meta) + 1}"
    entry = {"id": sid, "title": title, "created": time.time(), "updated": time.time()}
    meta.append(entry)
    _save_meta(meta)
    logger.info(f"新建会话: {sid} — {title}")
    return {"session": entry}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话（不能删 default）。"""
    _validate_session_id(session_id)
    if session_id == "default":
        raise HTTPException(400, "不能删除默认会话")
    meta = _load_meta()
    meta = [s for s in meta if s["id"] != session_id]
    _save_meta(meta)
    # 删除会话文件
    f = SESSIONS_DIR / f"{session_id}.json"
    if f.exists():
        f.unlink()
    logger.info(f"删除会话: {session_id}")
    return {"status": "ok"}


@router.get("/{session_id}/history")
async def get_session_history(session_id: str):
    """获取会话聊天记录。"""
    _validate_session_id(session_id)
    f = SESSIONS_DIR / f"{session_id}.json"
    if not f.exists():
        return {"messages": []}
    try:
        msgs = json.loads(f.read_text(encoding="utf-8"))
        return {"messages": msgs}
    except Exception:
        return {"messages": []}


@router.delete("/{session_id}/history")
async def clear_session_history(session_id: str):
    """清空会话聊天记录（保留会话本身）。"""
    _validate_session_id(session_id)
    f = SESSIONS_DIR / f"{session_id}.json"
    if f.exists():
        f.write_text("[]", encoding="utf-8")
    logger.info(f"清空会话历史: {session_id}")
    return {"status": "ok"}


@router.put("/{session_id}/title")
async def rename_session(session_id: str, req: CreateSessionRequest):
    """重命名会话。"""
    _validate_session_id(session_id)
    meta = _load_meta()
    for s in meta:
        if s["id"] == session_id:
            s["title"] = req.title or s["title"]
            s["updated"] = time.time()
            _save_meta(meta)
            return {"session": s}
    raise HTTPException(404, "会话不存在")
