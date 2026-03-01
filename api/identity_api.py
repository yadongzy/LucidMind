"""用户身份管理 API — 多用户灵魂系统。

端点:
  GET  /api/identity/{user_id}           — 获取用户身份信息
  GET  /api/identity/{user_id}/soul      — 获取用户灵魂
  PUT  /api/identity/{user_id}/soul      — 更新用户灵魂
  GET  /api/identity/{user_id}/profile   — 获取用户画像
  PUT  /api/identity/{user_id}/profile   — 更新用户画像
  GET  /api/identity/{user_id}/prompts   — 获取自定义提示词列表
  POST /api/identity/{user_id}/prompts   — 添加自定义提示词
  DELETE /api/identity/{user_id}/prompts/{name} — 删除自定义提示词
  GET  /api/identity/{user_id}/personas  — 获取用户自定义人格
  POST /api/identity/{user_id}/personas  — 添加用户自定义人格

注意: CORE.md 为系统级不可变文件，不通过写入 API 暴露。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from identity.user_identity import get_user_identity_manager

router = APIRouter(prefix="/api/identity", tags=["identity"])


class ContentBody(BaseModel):
    content: str


class PromptBody(BaseModel):
    name: str
    content: str


class PersonaBody(BaseModel):
    name: str
    content: str


@router.get("/{user_id}")
async def get_user_info(user_id: str):
    """获取用户身份信息摘要。"""
    mgr = get_user_identity_manager()
    return mgr.get_user_info(user_id)


@router.get("/{user_id}/soul")
async def get_soul(user_id: str):
    """获取用户灵魂文件内容。"""
    mgr = get_user_identity_manager()
    content = mgr.get_soul(user_id)
    return {"user_id": user_id, "content": content}


@router.put("/{user_id}/soul")
async def update_soul(user_id: str, body: ContentBody):
    """更新用户灵魂文件。"""
    mgr = get_user_identity_manager()
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="灵魂内容不能为空")
    ok = mgr.update_soul(user_id, body.content)
    if not ok:
        raise HTTPException(status_code=500, detail="灵魂更新失败")
    return {"success": True, "user_id": user_id}


@router.get("/{user_id}/profile")
async def get_profile(user_id: str):
    """获取用户画像。"""
    mgr = get_user_identity_manager()
    content = mgr.get_user_profile(user_id)
    return {"user_id": user_id, "content": content}


@router.put("/{user_id}/profile")
async def update_profile(user_id: str, body: ContentBody):
    """更新用户画像。"""
    mgr = get_user_identity_manager()
    ok = mgr.update_user_profile(user_id, body.content)
    if not ok:
        raise HTTPException(status_code=500, detail="画像更新失败")
    return {"success": True, "user_id": user_id}


@router.get("/{user_id}/prompts")
async def list_custom_prompts(user_id: str):
    """获取用户自定义提示词列表。"""
    mgr = get_user_identity_manager()
    prompts = mgr.get_custom_prompts(user_id)
    return {"user_id": user_id, "prompts": prompts}


@router.post("/{user_id}/prompts")
async def add_custom_prompt(user_id: str, body: PromptBody):
    """添加自定义提示词片段。"""
    mgr = get_user_identity_manager()
    if not body.name.strip() or not body.content.strip():
        raise HTTPException(status_code=400, detail="名称和内容不能为空")
    ok = mgr.add_custom_prompt(user_id, body.name, body.content)
    if not ok:
        raise HTTPException(status_code=500, detail="添加失败")
    return {"success": True, "user_id": user_id, "name": body.name}


@router.delete("/{user_id}/prompts/{name}")
async def delete_custom_prompt(user_id: str, name: str):
    """删除自定义提示词片段。"""
    mgr = get_user_identity_manager()
    ok = mgr.remove_custom_prompt(user_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"提示词 '{name}' 不存在")
    return {"success": True, "user_id": user_id, "name": name}


@router.get("/{user_id}/personas")
async def list_user_personas(user_id: str):
    """获取用户自定义人格列表。"""
    mgr = get_user_identity_manager()
    personas = mgr.get_user_personas(user_id)
    return {"user_id": user_id, "personas": personas}


@router.post("/{user_id}/personas")
async def add_user_persona(user_id: str, body: PersonaBody):
    """添加用户自定义人格。"""
    mgr = get_user_identity_manager()
    if not body.name.strip() or not body.content.strip():
        raise HTTPException(status_code=400, detail="名称和内容不能为空")
    ok = mgr.add_user_persona(user_id, body.name, body.content)
    if not ok:
        raise HTTPException(status_code=500, detail="添加失败")
    return {"success": True, "user_id": user_id, "name": body.name}
