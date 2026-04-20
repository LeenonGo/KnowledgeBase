"""系统配置 API（模型配置 + Prompt 管理）"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import AuditLog
from app.api.deps import get_current_user

router = APIRouter(prefix="/api", tags=["配置"])

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"
PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "prompts.json"


def _log_audit(db, user, action, resource="", detail="", status="success", ip=""):
    log = AuditLog(
        user_id=user.get("sub") if user else None,
        username=user.get("username") if user else "",
        action=action, resource=resource, detail=detail,
        ip_address=ip, status=status,
    )
    db.add(log)
    db.commit()


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
    _log_audit(db, user, "config_models", "模型配置", "已更新", "success",
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
