"""文件上传 API — 支持图片、文档、音视频。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from logs import get_logger

logger = get_logger("upload")

router = APIRouter()

# 上传目录
_UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 大小限制 (bytes)
_LIMITS = {
    "image": 6 * 1024 * 1024,       # 6MB
    "audio": 16 * 1024 * 1024,      # 16MB
    "video": 16 * 1024 * 1024,      # 16MB
    "document": 100 * 1024 * 1024,  # 100MB
}

# MIME → 类型映射
def _media_kind(mime: str) -> str:
    if not mime:
        return "unknown"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if mime in ("application/pdf",) or mime.startswith("text/"):
        return "document"
    if mime.startswith("application/"):
        return "document"
    return "unknown"


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """接收上传文件，保存到 data/uploads/，返回 file_id。"""
    if not file.filename:
        raise HTTPException(400, "No filename")

    mime = file.content_type or ""
    kind = _media_kind(mime)

    # 读取内容
    content = await file.read()
    size = len(content)

    # 大小检查
    limit = _LIMITS.get(kind, _LIMITS["document"])
    if size > limit:
        raise HTTPException(413, f"File too large: {size} bytes (limit {limit})")

    # 生成唯一 ID 并保存
    file_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix or ""
    save_name = f"{file_id}{ext}"
    save_path = _UPLOAD_DIR / save_name

    save_path.write_bytes(content)
    logger.info(f"文件上传: id={file_id}, name={file.filename}, size={size}, mime={mime}")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "path": str(save_path),
        "size": size,
        "mime": mime,
        "kind": kind,
    }


@router.get("/api/uploads")
async def list_uploads():
    """列出已上传的文件。"""
    files = []
    for f in sorted(_UPLOAD_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "path": str(f),
            })
    return {"files": files, "count": len(files)}
