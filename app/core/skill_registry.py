"""
Skill 注册中心 — 管理 Skill 的注册、查找、执行

支持三种 Skill 类型：
1. python: 直接调用 Python 函数
2. http: 调用外部 HTTP API
3. prompt: LLM + 工具链组合
"""

import json
import time
import importlib
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.models.models import Skill, SkillExecutionLog
from app.core.database import SessionLocal


class SkillRegistry:
    """Skill 注册中心 — 单例模式"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}  # name -> handler function
            cls._instance._cache = None
            cls._instance._cache_time = 0
        return cls._instance

    # ─── 注册 ────────────────────────────────────
    def register(self, name: str, handler, description: str = "",
                 category: str = "general", parameters_schema: dict = None):
        """注册内置 Skill handler"""
        self._handlers[name] = {
            "handler": handler,
            "description": description,
            "category": category,
            "parameters_schema": parameters_schema or {},
        }

    # ─── 获取定义（给 LLM） ─────────────────────
    def get_definitions(self, db=None, user_role: str = "user") -> list:
        """获取可用 Skill 定义列表（给 LLM 的 JSON Schema）"""
        import time as _time
        now = _time.time()

        # 5分钟缓存
        if self._cache and now - self._cache_time < 300:
            return self._cache

        defs = []
        if db:
            try:
                skills = db.query(Skill).filter(
                    Skill.is_enabled == True
                ).order_by(Skill.category, Skill.name).all()

                for s in skills:
                    # 权限检查
                    if not self._check_permission(s.required_role, user_role):
                        continue

                    params = {}
                    try:
                        params = json.loads(s.parameters_schema) if s.parameters_schema else {}
                    except:
                        pass

                    defs.append({
                        "type": "function",
                        "function": {
                            "name": s.name,
                            "description": s.description or s.display_name,
                            "parameters": params,
                        }
                    })
            except Exception as e:
                print(f"[SkillRegistry] 读取数据库 Skill 失败: {e}")

        self._cache = defs
        self._cache_time = now
        return defs

    # ─── 执行 ────────────────────────────────────
    def execute(self, name: str, arguments: dict, db=None, user: dict = None) -> str:
        """执行 Skill，返回结果文本"""
        start_time = time.time()

        # 1. 从数据库获取 Skill 定义
        skill_def = self._get_skill_def(name, db)
        if not skill_def:
            # 回退到内置 handler
            if name in self._handlers:
                try:
                    handler = self._handlers[name]["handler"]
                    result = handler(arguments) if not callable(handler) or handler.__code__.co_argcount <= 1 else handler(arguments, db, user)
                    self._log_execution(name, arguments, result, True, time.time() - start_time, db, user)
                    return result
                except Exception as e:
                    self._log_execution(name, arguments, str(e), False, time.time() - start_time, db, user)
                    return f"Skill 执行出错: {str(e)}"
            return f"未知 Skill: {name}"

        # 2. 根据 handler_type 执行
        handler_type = skill_def.get("handler_type", "python")
        handler_config = skill_def.get("handler_config", {})

        try:
            if handler_type == "python":
                result = self._execute_python(name, arguments, handler_config, db, user)
            elif handler_type == "http":
                result = self._execute_http(arguments, handler_config)
            elif handler_type == "prompt":
                result = self._execute_prompt(arguments, handler_config, db, user)
            else:
                result = f"不支持的 handler_type: {handler_type}"

            # 更新统计
            latency_ms = int((time.time() - start_time) * 1000)
            self._update_stats(name, latency_ms, db)
            self._log_execution(name, arguments, result[:200], True, latency_ms, db, user)
            return result

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            self._log_execution(name, arguments, str(e), False, latency_ms, db, user)
            return f"Skill 执行出错: {str(e)}"

    # ─── 内部方法 ────────────────────────────────
    def _get_skill_def(self, name: str, db=None) -> Optional[dict]:
        """从数据库获取 Skill 定义"""
        if not db:
            return None
        try:
            skill = db.query(Skill).filter(Skill.name == name, Skill.is_enabled == True).first()
            if not skill:
                return None
            return {
                "name": skill.name,
                "handler_type": skill.handler_type,
                "handler_config": json.loads(skill.handler_config) if skill.handler_config else {},
                "parameters_schema": json.loads(skill.parameters_schema) if skill.parameters_schema else {},
            }
        except:
            return None

    def _execute_python(self, name: str, arguments: dict, config: dict, db, user) -> str:
        """执行 Python 类型 Skill"""
        # 优先使用注册的 handler
        if name in self._handlers:
            handler = self._handlers[name]["handler"]
            if callable(handler):
                import inspect
                sig = inspect.signature(handler)
                params = list(sig.parameters.keys())
                if len(params) <= 1:
                    return handler(arguments)
                elif len(params) <= 2:
                    return handler(arguments, db)
                else:
                    return handler(arguments, db, user)

        # 动态加载模块
        module_path = config.get("module", "")
        func_name = config.get("function", "")
        if module_path and func_name:
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            import inspect
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) <= 1:
                return func(arguments)
            elif len(params) <= 2:
                return func(arguments, db)
            else:
                return func(arguments, db, user)

        return f"Python Skill {name} 未找到执行函数"

    def _execute_http(self, arguments: dict, config: dict) -> str:
        """执行 HTTP 类型 Skill"""
        import httpx
        url = config.get("url", "")
        method = config.get("method", "POST").upper()
        headers = json.loads(config.get("headers", "{}"))

        if not url:
            return "HTTP Skill 未配置 URL"

        with httpx.Client(timeout=30) as client:
            if method == "GET":
                resp = client.get(url, params=arguments, headers=headers)
            else:
                resp = client.post(url, json=arguments, headers=headers)
            return resp.text

    def _execute_prompt(self, arguments: dict, config: dict, db, user) -> str:
        """执行 Prompt 类型 Skill（LLM + 工具链）"""
        from app.core.llm import get_llm_client, get_prompt

        system_prompt = config.get("system", "你是一个智能助手。")
        user_template = config.get("template", "{input}")
        tool_chain = config.get("tools", [])

        # 构建用户消息
        user_msg = user_template.format(**arguments) if arguments else user_template

        client, model, cfg = get_llm_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        # 如果有工具链，注入工具
        kwargs = {"model": model, "messages": messages, "max_tokens": 4096, "temperature": 0.7}
        if tool_chain:
            from app.core.tools import registry
            all_defs = registry.get_definitions(db)
            available = [d for d in all_defs if d["function"]["name"] in tool_chain]
            if available:
                kwargs["tools"] = available
                kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _check_permission(self, required_role: str, user_role: str) -> bool:
        """检查权限"""
        role_hierarchy = {"user": 0, "kb_admin": 1, "super_admin": 2}
        return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)

    def _update_stats(self, name: str, latency_ms: int, db=None):
        """更新 Skill 统计"""
        if not db:
            return
        try:
            skill = db.query(Skill).filter(Skill.name == name).first()
            if skill:
                # 移动平均延迟
                if skill.avg_latency_ms == 0:
                    skill.avg_latency_ms = latency_ms
                else:
                    skill.avg_latency_ms = skill.avg_latency_ms * 0.8 + latency_ms * 0.2
                skill.usage_count += 1
                skill.last_used_at = datetime.now()
                db.commit()
        except:
            db.rollback()

    def _log_execution(self, name: str, arguments: dict, result: str,
                       success: bool, latency_ms: float, db=None, user: dict = None):
        """记录执行日志"""
        if not db:
            return
        try:
            log = SkillExecutionLog(
                skill_id=self._get_skill_id(name, db),
                user_id=user.get("sub") if user else None,
                arguments=json.dumps(arguments, ensure_ascii=False)[:2000],
                result_preview=result[:200],
                success=success,
                latency_ms=int(latency_ms),
            )
            db.add(log)
            db.commit()
        except:
            db.rollback()

    def _get_skill_id(self, name: str, db=None) -> Optional[str]:
        """获取 Skill ID"""
        if not db:
            return None
        try:
            skill = db.query(Skill).filter(Skill.name == name).first()
            return skill.id if skill else None
        except:
            return None

    def clear_cache(self):
        """清除缓存"""
        self._cache = None
        self._cache_time = 0


# 全局实例
skill_registry = SkillRegistry()
