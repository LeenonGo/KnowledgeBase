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
PROMPTS_DIR = Path(__file__).parent.parent.parent / "config" / "prompts"
GENERAL_PATH = Path(__file__).parent.parent.parent / "config" / "general.json"



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


# Prompt key -> 所属文件映射
_PROMPT_FILE_MAP = {
    "qa": "core", "rewrite": "core", "refuse": "core", "polish": "core",
    "agent": "agent", "planner": "agent", "synthesizer": "agent",
    "sql_generate": "sql", "sql_analyze": "sql",
    "kg_extract": "kg", "kg_entity_recognize": "kg",
}


@router.get("/config/prompts")
async def get_prompts(user: dict = Depends(get_current_user)):
    """合并读取所有 prompt 文件，返回统一 dict"""
    merged = {}
    if PROMPTS_DIR.is_dir():
        for p in sorted(PROMPTS_DIR.glob("*.json")):
            with open(p, "r", encoding="utf-8") as f:
                merged.update(json.load(f))
    # 向后兼容：单文件
    legacy = PROMPTS_DIR.parent / "prompts.json"
    if legacy.exists():
        with open(legacy, "r", encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged


@router.post("/config/prompts")
async def save_prompts(data: dict, user: dict = Depends(get_current_user)):
    """将合并的 dict 拆分写入对应的模块文件"""
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    # 按文件分组
    file_groups = {}
    for key, val in data.items():
        file_name = _PROMPT_FILE_MAP.get(key, "core")
        file_groups.setdefault(file_name, {})[key] = val
    # 写入各文件
    for file_name, prompts in file_groups.items():
        file_path = PROMPTS_DIR / f"{file_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
    return {"message": "Prompt 已保存"}


@router.get("/config/general")
async def get_general_config(user: dict = Depends(get_current_user)):
    if GENERAL_PATH.exists():
        with open(GENERAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@router.post("/config/general")
async def save_general_config(data: dict, user: dict = Depends(get_current_user)):
    GENERAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GENERAL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"message": "通用设置已保存"}
