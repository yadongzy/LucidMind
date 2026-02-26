"""Persona API — 多角色/分身管理接口。"""

from fastapi import APIRouter
from pydantic import BaseModel

from identity.personas import get_persona_manager

router = APIRouter(prefix="/api/persona", tags=["persona"])


class CreatePersonaRequest(BaseModel):
    name: str
    description: str
    traits: str = ""
    expertise: str = ""


class SwitchPersonaRequest(BaseModel):
    name: str


@router.get("/list")
async def list_personas():
    """列出所有可用人格。"""
    pm = get_persona_manager()
    return {"personas": pm.list_personas(), "current": pm.get_current()}


@router.post("/switch")
async def switch_persona(req: SwitchPersonaRequest):
    """切换当前人格。"""
    pm = get_persona_manager()
    result = pm.switch(req.name)
    return result


@router.post("/create")
async def create_persona(req: CreatePersonaRequest):
    """创建新人格。"""
    pm = get_persona_manager()
    result = pm.create(req.name, req.description, req.traits, req.expertise)
    return result


@router.delete("/{name}")
async def delete_persona(name: str):
    """删除人格。"""
    pm = get_persona_manager()
    result = pm.delete(name)
    return result
