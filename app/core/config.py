"""配置加载"""

import json
from pathlib import Path

from app.models.schema import ModelsConfig

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.json"


def load_config() -> ModelsConfig:
    """加载模型配置"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ModelsConfig(**data)
