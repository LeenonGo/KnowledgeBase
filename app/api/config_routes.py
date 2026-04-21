"""系统配置 API（模型配置 + Prompt 管理）"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import AuditLog
from app.api.deps import get_current_user, log_audit

router = APIRouter(prefix="/api", tags=["配置"])

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"
PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "prompts.json"



@router.get("/config/models")
async def get_model_config(user: dict = Depends(get_current_user)):
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"llm": {}, "embedding": {}}


@router.post("/config/models")
async def save_model_config(data: dict, request: Request,
                            db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log_audit(db, user, "config_models", "模型配置", "已更新", "success",
               request.client.host if request.client else "")
    return {"message": "配置已保存"}


@router.get("/config/prompts")
async def get_prompts(user: dict = Depends(get_current_user)):
    if PROMPTS_PATH.exists():
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@router.post("/config/prompts")
async def save_prompts(data: dict, user: dict = Depends(get_current_user)):
    PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"message": "Prompt 已保存"}
