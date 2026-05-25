"""迁移脚本：创建 skill + skill_execution_log 表，迁移内置工具为 Skill"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine, SessionLocal
from app.models.models import Skill, SkillExecutionLog, Base


# 内置 Skill 定义
BUILTIN_SKILLS = [
    {
        "name": "knowledge_search",
        "display_name": "知识库检索",
        "description": "在知识库中搜索相关文档内容。当用户问题涉及知识库中的信息时使用。",
        "category": "retrieval",
        "icon": "🔍",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_search_kb"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "kb_id": {"type": "string", "description": "知识库 ID，不填则搜索全部"},
                "top_k": {"type": "integer", "description": "返回数量，默认 5"}
            },
            "required": ["query"]
        }),
    },
    {
        "name": "list_kb",
        "display_name": "列出知识库",
        "description": "列出当前用户可访问的所有知识库。",
        "category": "retrieval",
        "icon": "📂",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_list_kb"}),
        "parameters_schema": json.dumps({"type": "object", "properties": {}, "required": []}),
    },
    {
        "name": "web_search",
        "display_name": "联网搜索",
        "description": "搜索互联网获取最新信息。当知识库中没有相关内容或用户需要最新信息时使用。",
        "category": "retrieval",
        "icon": "🌐",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_web_search"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询关键词"}
            },
            "required": ["query"]
        }),
    },
    {
        "name": "sql_query",
        "display_name": "SQL 数据分析",
        "description": "用自然语言查询电商数据库。支持多表关联、聚合、排序。",
        "category": "analysis",
        "icon": "📊",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_sql_query"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "自然语言问题"}
            },
            "required": ["question"]
        }),
    },
    {
        "name": "chart_generator",
        "display_name": "图表生成",
        "description": "根据数据自动生成可视化图表（柱状图/折线图/饼图）。",
        "category": "generation",
        "icon": "📈",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_chart_generator"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "数据，如 '北京:100,上海:200,广州:150'"},
                "chart_type": {"type": "string", "enum": ["bar", "line", "pie"], "description": "图表类型"},
                "title": {"type": "string", "description": "图表标题"}
            },
            "required": ["data"]
        }),
    },
    {
        "name": "calculator",
        "display_name": "数学计算",
        "description": "精确数学计算。当需要进行数值计算、公式求值时使用。",
        "category": "utility",
        "icon": "🔢",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_calculator"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式，如 2+3*4"}
            },
            "required": ["expression"]
        }),
    },
    {
        "name": "current_time",
        "display_name": "当前时间",
        "description": "获取当前日期和时间（北京时间）。",
        "category": "utility",
        "icon": "🕐",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_current_time"}),
        "parameters_schema": json.dumps({"type": "object", "properties": {}, "required": []}),
    },
    {
        "name": "http_request",
        "display_name": "HTTP 请求",
        "description": "发送 HTTP 请求访问外部 API。支持 GET/POST，有 SSRF 防护。",
        "category": "utility",
        "icon": "🔗",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_http_request"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL"},
                "method": {"type": "string", "enum": ["GET", "POST"], "description": "请求方法"},
                "headers": {"type": "string", "description": "JSON 格式的请求头"},
                "body": {"type": "string", "description": "POST 请求体"}
            },
            "required": ["url"]
        }),
    },
    {
        "name": "recall_memory",
        "display_name": "用户记忆检索",
        "description": "查询当前用户的记忆信息（偏好、背景、纠正记录）。",
        "category": "memory",
        "icon": "🧠",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_recall_memory"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "memory_type": {"type": "string", "enum": ["preference", "context", "correction", "all"], "description": "记忆类型"}
            }
        }),
    },
    {
        "name": "search_faq",
        "display_name": "FAQ 检索",
        "description": "检索 FAQ 高频问答库。当问题可能是常见问题时使用。",
        "category": "retrieval",
        "icon": "❓",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_search_faq"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词"}
            },
            "required": ["query"]
        }),
    },
    {
        "name": "doc_stats",
        "display_name": "文档统计",
        "description": "获取知识库的统计信息（文档数、分块数、格式分布等）。",
        "category": "analysis",
        "icon": "📋",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_doc_stats"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "kb_id": {"type": "string", "description": "知识库 ID。不填则统计全部"}
            }
        }),
    },
    {
        "name": "knowledge_compare",
        "display_name": "知识对比",
        "description": "对比两个知识库或文档的内容差异。",
        "category": "analysis",
        "icon": "⚖️",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_knowledge_compare"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "来源1"},
                "target": {"type": "string", "description": "来源2"},
                "query": {"type": "string", "description": "对比维度"}
            },
            "required": ["source", "target"]
        }),
    },
    {
        "name": "search_kg",
        "display_name": "知识图谱查询",
        "description": "在知识图谱中检索实体和关系。当问题涉及实体间关系、多跳推理时使用。",
        "category": "retrieval",
        "icon": "🕸️",
        "handler_type": "python",
        "handler_config": json.dumps({"module": "app.core.tools", "function": "_search_kg"}),
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "实体名称"},
                "kb_id": {"type": "string", "description": "知识库 ID"},
                "hops": {"type": "integer", "description": "查询跳数，1-2，默认1"}
            },
            "required": ["entity"]
        }),
    },
]


def migrate():
    print("创建 skill + skill_execution_log 表...")
    Skill.__table__.create(engine, checkfirst=True)
    try:
        SkillExecutionLog.__table__.create(engine, checkfirst=True)
    except:
        pass
    print("✅ 表创建完成")

    db = SessionLocal()
    try:
        count = db.query(Skill).count()
        if count > 0:
            print(f"⏭️  表中已有 {count} 条 Skill 记录，跳过迁移")
            return

        print(f"迁移 {len(BUILTIN_SKILLS)} 个内置 Skill...")
        for skill_data in BUILTIN_SKILLS:
            skill = Skill(
                is_builtin=True,
                is_enabled=True,
                **skill_data
            )
            db.add(skill)
            print(f"  ✅ {skill_data['display_name']}")

        db.commit()
        print("✅ 内置 Skill 迁移完成")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
