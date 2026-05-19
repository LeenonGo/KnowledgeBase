"""
SQL Agent 核心引擎 — Text-to-SQL

功能：
  - Schema 提取：从 MySQL 读取表结构
  - SQL 生成：自然语言 → SQL（LLM）
  - SQL 校验：安全检查 + EXPLAIN 验证
  - SQL 执行：安全执行 + 结构化返回
  - 分析总结：LLM 基于结果生成洞察
  - 多轮追问：支持历史上下文
"""

import json
import re
import time
import logging
from typing import Generator, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pymysql

logger = logging.getLogger("kb.sql_agent")

# ═══════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════

import os

def get_sql_agent_db_config():
    """获取 SQL Agent 数据库连接配置"""
    url = os.getenv("SQL_AGENT_DB_URL", "")
    if not url:
        raise ValueError("未配置 SQL_AGENT_DB_URL")
    url = url.replace("mysql+pymysql://", "")
    if "@" in url:
        auth, rest = url.split("@", 1)
        user, password = auth.split(":", 1)
    else:
        user, password = "root", ""
        rest = url
    if "/" in rest:
        host_port, dbname = rest.split("/", 1)
        dbname = dbname.split("?")[0]
    else:
        host_port, dbname = rest, "ecommerce_demo"
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host, port = host_port, 3306
    return {"host": host, "port": port, "user": user, "password": password, "database": dbname}


def get_db_connection():
    """获取数据库连接"""
    cfg = get_sql_agent_db_config()
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


# ═══════════════════════════════════════════════════
# Schema 提取器
# ═══════════════════════════════════════════════════

class SchemaExtractor:
    """从 MySQL 提取表结构信息"""

    def __init__(self):
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = 300  # 5 分钟

    def get_schema_text(self, force_refresh=False) -> str:
        """返回格式化的 Schema 文本（markdown），注入 LLM prompt 用"""
        if self._cache and not force_refresh and time.time() - self._cache_time < self._cache_ttl:
            return self._cache

        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # 获取所有表
            cur.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cur.fetchall()]

            lines = []
            relations = []

            for table in tables:
                # 表注释
                cur.execute(f"SHOW TABLE STATUS LIKE '{table}'")
                status = cur.fetchone()
                table_comment = status.get("Comment", "") if status else ""

                # 列信息
                cur.execute(f"DESCRIBE `{table}`")
                columns = cur.fetchall()

                lines.append(f"### Table: {table}")
                if table_comment:
                    lines.append(f"说明：{table_comment}")
                lines.append("| 列名 | 类型 | 可空 | 说明 |")
                lines.append("|------|------|------|------|")

                for col in columns:
                    col_name = col["Field"]
                    col_type = col["Type"]
                    nullable = "YES" if col["Null"] == "YES" else "NO"
                    col_comment = col.get("Comment", "") or ""
                    extra = col.get("Extra", "")
                    if "auto_increment" in extra:
                        col_comment = "主键(自增)" if not col_comment else col_comment
                    if col["Key"] == "PRI":
                        col_comment = "🔑 " + col_comment
                    elif col["Key"] == "MUL":
                        col_comment = "🔗 " + col_comment
                    lines.append(f"| {col_name} | {col_type} | {nullable} | {col_comment} |")

                # 行数
                cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
                row_cnt = cur.fetchone()["cnt"]
                lines.append(f"当前数据量：{row_cnt} 行")

                # 外键关系
                cur.execute(f"""
                    SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """)
                fks = cur.fetchall()
                for fk in fks:
                    relations.append(
                        f"- {table}.{fk['COLUMN_NAME']} → {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                    )

                lines.append("")

            if relations:
                lines.append("### 表关联关系")
                lines.extend(relations)
                lines.append("")

            self._cache = "\n".join(lines)
            self._cache_time = time.time()
            return self._cache

        finally:
            conn.close()

    def get_schema_struct(self) -> dict:
        """返回结构化的 Schema（供前端展示）"""
        conn = get_db_connection()
        try:
            cur = conn.cursor()

            cur.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cur.fetchall()]

            result_tables = []
            result_relations = []

            for table in tables:
                cur.execute(f"SHOW TABLE STATUS LIKE '{table}'")
                status = cur.fetchone()
                table_comment = status.get("Comment", "") if status else ""

                cur.execute(f"DESCRIBE `{table}`")
                columns = cur.fetchall()

                cols = []
                for col in columns:
                    cols.append({
                        "name": col["Field"],
                        "type": col["Type"],
                        "nullable": col["Null"] == "YES",
                        "key": col["Key"],
                        "comment": col.get("Comment", ""),
                    })

                cur.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
                row_cnt = cur.fetchone()["cnt"]

                result_tables.append({
                    "name": table,
                    "comment": table_comment,
                    "columns": cols,
                    "row_count": row_cnt,
                })

                cur.execute(f"""
                    SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}'
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """)
                for fk in cur.fetchall():
                    result_relations.append({
                        "from": f"{table}.{fk['COLUMN_NAME']}",
                        "to": f"{fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}",
                        "type": "N:1",
                    })

            return {"tables": result_tables, "relations": result_relations}

        finally:
            conn.close()


# ═══════════════════════════════════════════════════
# SQL 校验 & 执行
# ═══════════════════════════════════════════════════

class SQLExecutor:
    """安全的 SQL 执行引擎"""

    DANGEROUS_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
        'TRUNCATE', 'REPLACE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'LOAD', 'OUTFILE', 'DUMPFILE', 'SLEEP', 'BENCHMARK',
    ]

    def validate(self, sql: str) -> dict:
        """三层安全校验"""
        sql_clean = sql.strip().rstrip(';')
        sql_upper = sql_clean.upper()

        # ① 必须以 SELECT 或 WITH 开头
        if not re.match(r'^\s*(SELECT|WITH)\s', sql_upper):
            return {"valid": False, "error": "只允许 SELECT 查询语句"}

        # ② 关键词黑名单
        # 去掉字符串中的内容避免误判
        sql_no_strings = re.sub(r"'[^']*'", "''", sql_upper)
        sql_no_strings = re.sub(r'"[^"]*"', '""', sql_no_strings)
        for kw in self.DANGEROUS_KEYWORDS:
            # 用单词边界匹配
            if re.search(rf'\b{kw}\b', sql_no_strings):
                return {"valid": False, "error": f"包含危险关键词: {kw}"}

        # ③ 注入检测：检查常见注入模式
        injection_patterns = [
            (r'UNION\s+ALL\s+SELECT.*--', '疑似 SQL 注入'),   # UNION 注释
            (r'OR\s+1\s*=\s*1', '疑似 SQL 注入'),             # 永真条件
        ]
        for pat, msg in injection_patterns:
            if re.search(pat, sql_upper):
                return {"valid": False, "error": msg}

        # ④ 检测多语句（LLM 幻觉：把多个 SQL 拼在一起）— 自动截取第一条
        if re.search(r';\s*(SELECT|WITH|INSERT|UPDATE|DELETE|DROP)', sql_upper):
            # 截取第一个分号之前的内容
            first_sql = re.split(r';\s*(?:SELECT|WITH|INSERT|UPDATE|DELETE|DROP)', sql_upper, 1)[0]
            if first_sql.strip():
                logger.warning(f"[SQL Validate] 检测到多语句，自动截取第一条: {sql_clean[:60]}...")
                sql_clean = first_sql.strip()
                sql_upper = sql_clean.upper()
            else:
                return {"valid": False, "error": "只允许单条 SELECT 语句"}

        return {"valid": True, "sql": sql_clean}



    def _get_table_columns(self, table_name: str) -> list:
        """获取表的实际列名"""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(f"DESCRIBE `{table_name}`")
            columns = [row['Field'].lower() for row in cur.fetchall()]
            cur.close()
            conn.close()
            return columns
        except:
            return []

    def _check_permission(self, sql: str, user_role: str, default_limit: int) -> dict:
        """检查 SQL 表级权限"""
        import re
        from app.core.database import SessionLocal
        from app.models.models import SqlTablePermission
        
        # 解析 SQL 中的表名
        sql_upper = sql.upper()
        tables = set()
        # 匹配 FROM table 和 JOIN table
        for match in re.finditer(r'\b(?:FROM|JOIN)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?', sql_upper):
            tables.add(match.group(1).lower())
        
        if not tables:
            return {"allowed": True, "max_rows": default_limit}
        
        db = SessionLocal()
        try:
            # 获取该角色的所有权限
            perms = db.query(SqlTablePermission).filter(SqlTablePermission.role == user_role).all()
            perm_map = {p.table_name: p for p in perms}
            
            for table in tables:
                perm = perm_map.get(table)
                if perm:
                    if not perm.can_query:
                        return {"allowed": False, "error": f"无权查询表 {table}"}
                    # 检查禁止列（需要先获取表的实际列名映射）
                    if perm.columns_deny:
                        deny_cols = [c.strip().lower() for c in perm.columns_deny.split(",") if c.strip()]
                        # 获取表的实际列名
                        actual_cols = self._get_table_columns(table)
                        for deny_col in deny_cols:
                            # 检查 SQL 中是否引用了禁止的列
                            # 1. 直接匹配列名：cost_price 或 table.cost_price
                            if re.search(rf'`?{deny_col}`?|{table}\.`?{deny_col}`?', sql.lower()):
                                return {"allowed": False, "error": f"无权查询表 {table} 的列 {deny_col}"}
                            # 2. 检查是否有列的别名映射到禁止列
                            # 例如：cost_price AS 成本价，SQL中写成 cost AS 成本价
                            # 通过检查 SELECT 子句中的列是否在禁止列表中
                            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
                            if select_match:
                                select_cols = select_match.group(1)
                                # 检查是否有 AS 别名映射到禁止列
                                for actual_col in actual_cols:
                                    if actual_col.lower() == deny_col:
                                        # 检查这个列是否在 SELECT 中（可能用别名）
                                        if re.search(rf'`?{actual_col}`?\s+AS', select_cols, re.IGNORECASE):
                                            return {"allowed": False, "error": f"无权查询表 {table} 的列 {deny_col}"}
                                        # 也检查直接引用
                                        if re.search(rf'\b{actual_col}\b', select_cols, re.IGNORECASE):
                                            return {"allowed": False, "error": f"无权查询表 {table} 的列 {deny_col}"}
                else:
                    # 没有配置的表，默认允许（super_admin 可以配置所有表）
                    pass
            
            # 计算最大行数（取所有涉及表的最小值）
            max_rows = default_limit
            for table in tables:
                perm = perm_map.get(table)
                if perm and perm.can_query:
                    max_rows = min(max_rows, perm.max_rows)
            
            return {"allowed": True, "max_rows": max_rows}
        finally:
            db.close()

    def execute(self, sql: str, limit: int = 500, user_role: str = None) -> dict:
        """安全执行 SQL 查询"""
        # 校验
        validation = self.validate(sql)
        if not validation["valid"]:
            return {"error": validation["error"]}

        sql_clean = validation["sql"]

        # 权限校验
        if user_role and user_role != "super_admin":
            perm_result = self._check_permission(sql_clean, user_role, limit)
            if not perm_result["allowed"]:
                return {"error": perm_result["error"]}
            limit = min(limit, perm_result["max_rows"])

        # 处理 LIMIT：确保不超过权限允许的 max_rows
        import re
        limit_match = re.search(r'\bLIMIT\s+(\d+)', sql_clean, re.IGNORECASE)
        if limit_match:
            current_limit = int(limit_match.group(1))
            if current_limit > limit:
                sql_clean = re.sub(r'\bLIMIT\s+\d+', f'LIMIT {limit}', sql_clean, flags=re.IGNORECASE)
        else:
            sql_clean += f' LIMIT {limit}'

        conn = get_db_connection()
        try:
            cur = conn.cursor()

            # EXPLAIN 预检
            try:
                cur.execute(f"EXPLAIN {sql_clean}")
            except Exception as e:
                return {"error": f"SQL 语法错误: {str(e)}"}

            # 执行
            start = time.time()
            cur.execute(sql_clean)
            rows = cur.fetchall()
            elapsed_ms = int((time.time() - start) * 1000)

            if not rows:
                return {"columns": [], "rows": [], "row_count": 0, "elapsed_ms": elapsed_ms}

            columns = list(rows[0].keys())
            # 序列化 Decimal / Date 等类型
            serialized_rows = []
            for row in rows:
                serialized_row = []
                for v in row.values():
                    if hasattr(v, 'isoformat'):  # datetime/date
                        serialized_row.append(v.isoformat())
                    elif isinstance(v, Decimal):
                        serialized_row.append(float(v))
                    else:
                        serialized_row.append(v)
                serialized_rows.append(serialized_row)

            return {
                "columns": columns,
                "rows": serialized_rows,
                "row_count": len(serialized_rows),
                "elapsed_ms": elapsed_ms,
            }

        except Exception as e:
            logger.error(f"SQL 执行异常: {e}", exc_info=True)
            return {"error": f"执行异常: {str(e)}"}
        finally:
            conn.close()


# ═══════════════════════════════════════════════════
# SQL 生成器
# ═══════════════════════════════════════════════════

def _get_sql_prompt(prompt_type: str, default_key: str) -> dict:
    """从配置加载 SQL 相关 prompt，失败则用内置默认值"""
    try:
        from app.core.config import load_prompts_config
        prompts = load_prompts_config()
        if prompt_type in prompts:
            return prompts[prompt_type]
    except Exception:
        pass
    return SQL_DEFAULT_PROMPTS[default_key]


SQL_DEFAULT_PROMPTS = {
    "generate": {
        "system": """你是一个 MySQL SQL 专家。根据用户的自然语言问题，生成准确的查询语句。

## 数据库表结构
{schema}

## 规则
1. 只生成 SELECT 语句（允许 WITH ... SELECT），不允许任何数据修改操作
2. 使用有意义的中文列别名提升可读性，例如 `SUM(amount) AS '总金额'`
3. 结果默认 LIMIT 500，除非用户明确要求全量数据
4. 如果问题涉及时间，使用 NOW()、DATE_SUB() 等函数动态计算当前相对时间
5. 多表关联时使用明确的 JOIN ... ON 语法
6. 如果问题有歧义，选择最合理的解释
7. GROUP BY 严格模式（only_full_group_by）：
   - SELECT 中的每个非聚合列（无 SUM/COUNT/AVG 等函数包裹的列）必须出现在 GROUP BY 中
   - 当用 CASE WHEN 或表达式分组时，SELECT 中也要用相同的表达式，不能直接引用原字段
   - 正确示例：`SELECT CASE WHEN x THEN 'A' ELSE 'B' END AS type, COUNT(*) ... GROUP BY CASE WHEN x THEN 'A' ELSE 'B' END`
   - 错误示例：`SELECT CASE WHEN x THEN 'A' ELSE 'B' END AS type, x, COUNT(*) ... GROUP BY CASE WHEN x THEN 'A' ELSE 'B' END`（x 没在 GROUP BY 中）

## 输出格式（严格 JSON）
```json
{{
    "sql": "SELECT ...",
    "thinking": "用户的意图是...，我选择了这些表和关联方式因为..."
}}
```

只输出 JSON，不要有其他文字。"""
    },
    "analyze": {
        "system": """你是一个数据分析师。根据以下查询结果，给出简洁的分析总结。

## 用户问题
{question}

## 执行的 SQL
```sql
{sql}
```

## 查询结果（前 20 行）
{result_preview}

## 输出格式（严格 JSON）
```json
{{
    "summary": "2-3句话的分析总结，包含关键数字",
    "highlights": ["关键发现1", "关键发现2"],
    "chart": {{
        "type": "bar|line|pie",
        "title": "图表标题",
        "x_col": "X轴列名",
        "y_col": "Y轴列名"
    }}
```

如果数据不适合图表，chart 设为 null。
只输出 JSON，不要有其他文字。"""
    }
}


class SQLGenerator:
    """LLM 驱动的 SQL 生成器"""

    def generate(self, question: str, schema: str, history: list = None) -> dict:
        from app.core.llm import get_llm_client

        client, model, cfg = get_llm_client()

        messages = [
            {"role": "system", "content": _get_sql_prompt("sql_generate", "generate")["system"].format(schema=schema)},
        ]

        # 加入历史上下文
        if history:
            messages.extend(history[-6:])  # 最近 3 轮

        messages.append({"role": "user", "content": question})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=cfg.get("max_tokens", 2048),
            temperature=0.1,  # 低温度，SQL 需要精确
        )

        content = (response.choices[0].message.content or "").strip()

        if not content:
            return {"sql": "", "thinking": "模型返回为空，请检查 max_tokens 配置"}
        # 提取 JSON
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)

        try:
            result = json.loads(content)
            if "sql" not in result:
                result["sql"] = content
                result["thinking"] = "无法解析思考过程"
            # 修复字面量换行 + 压缩为单行
            sql = result.get("sql", "")
            if '\\n' in sql:
                sql = sql.replace('\\n', '\n')
            result["sql"] = re.sub(r'\s+', ' ', sql).strip()
            return result
        except json.JSONDecodeError:
            # 尝试从内容中提取 SQL
            sql_match = re.search(r'(SELECT\b.+?)(?:\n\n|$)', content, re.DOTALL | re.IGNORECASE)
            if sql_match:
                return {"sql": sql_match.group(1).strip(), "thinking": "从响应中提取 SQL"}
            return {"sql": content, "thinking": "直接返回模型输出"}

    def generate_with_retry(self, question: str, schema: str,
                            executor: SQLExecutor, history: list = None,
                            max_retries: int = 3) -> dict:
        """带错误重试的 SQL 生成"""
        messages = [
            {"role": "system", "content": _get_sql_prompt("sql_generate", "generate")["system"].format(schema=schema)},
        ]
        if history:
            messages.extend(history[-6:])

        messages.append({"role": "user", "content": question})

        from app.core.llm import get_llm_client
        client, model, cfg = get_llm_client()

        for attempt in range(max_retries):
            _t0 = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=cfg.get("max_tokens", 2048),
                temperature=0.1,
            )
            _t_llm = time.time() - _t0
            content = (response.choices[0].message.content or "").strip()
            content = re.sub(r'```json\s*', '', content)
            if not content:
                messages.append({"role": "assistant", "content": ""})
                messages.append({"role": "user", "content": "你返回了空内容，请重新输出 JSON。"})
                logger.info(f"[SQL Gen] 尝试 {attempt+1}: 空响应, LLM耗时 {_t_llm:.1f}s")
                continue
            content = re.sub(r'```\s*$', '', content)

            try:
                result = json.loads(content)
                sql = result.get("sql", content)
                thinking = result.get("thinking", "")
            except json.JSONDecodeError:
                sql_match = re.search(r'(SELECT\b.+?)(?:\n\n|$)', content, re.DOTALL | re.IGNORECASE)
                sql = sql_match.group(1).strip() if sql_match else content
                thinking = ""

            # 修复 LLM 返回的 SQL 中字面量 \n（反斜杠+n）→ 真实换行
            if '\\n' in sql:
                sql = sql.replace('\\n', '\n')
                logger.info(f"[SQL Gen] 已修复字面量换行符")
            # SQL 压缩为单行，避免驱动对换行/空白敏感
            sql = re.sub(r'\s+', ' ', sql).strip()

            # 校验
            validation = executor.validate(sql)
            if validation["valid"]:
                logger.info(f"[SQL Gen] 尝试 {attempt+1}: 成功, LLM耗时 {_t_llm:.1f}s")
                return {"sql": sql, "thinking": thinking, "attempts": attempt + 1}

            # 校验失败，把错误反馈给 LLM
            logger.warning(f"[SQL Gen] 尝试 {attempt+1}: 校验失败 ({validation['error']}), LLM耗时 {_t_llm:.1f}s")
            messages.append({"role": "assistant", "content": json.dumps({"sql": sql, "thinking": thinking})})
            messages.append({"role": "user", "content": f"SQL 有问题：{validation['error']}，请修正后重新输出 JSON。"})

        # 全部重试失败，返回最后一次结果
        return {"sql": sql, "thinking": thinking, "attempts": max_retries,
                "warning": f"SQL 校验未通过，已重试 {max_retries} 次"}


# ═══════════════════════════════════════════════════
# 分析总结器
# ═══════════════════════════════════════════════════

class AnalysisGenerator:
    """基于查询结果生成分析总结，支持多种输出格式"""

    # 结构化输出 Prompt 模板
    FORMAT_PROMPTS = {
        "table": """
## 输出格式（严格 JSON）
```json
{{
    "summary": "2-3句话的分析总结，包含关键数字",
    "highlights": ["关键发现1", "关键发现2"],
    "chart": {{
        "type": "bar|line|pie",
        "title": "图表标题",
        "x_col": "X轴列名",
        "y_col": "Y轴列名"
    }}
}}
```
如果数据不适合图表，chart 设为 null。
只输出 JSON，不要有其他文字。""",
        "json": """
## 输出格式（严格 JSON）
```json
{{
    "summary": "一句话总结",
    "data": [
        {{"字段1": 值1, "字段2": 值2}}
    ],
    "schema": {{
        "字段1": "类型说明",
        "字段2": "类型说明"
    }}
}}
```
data 中每项是一个对象，key 用中文字段名。schema 描述每个字段的含义和类型。
只输出 JSON，不要有其他文字。""",
        "report": """
## 输出格式（严格 JSON）
```json
{{
    "title": "分析报告标题",
    "summary": "执行摘要：核心结论（2-3句话）",
    "sections": [
        {{
            "heading": "分节标题",
            "content": "该节的详细分析",
            "data": [{{"指标": "值", "说明": "解读"}}]
        }}
    ],
    "conclusion": "结论与建议",
    "chart": {{
        "type": "bar|line|pie",
        "title": "图表标题",
        "x_col": "X轴列名",
        "y_col": "Y轴列名"
    }}
}}
```
如果数据不适合图表，chart 设为 null。
只输出 JSON，不要有其他文字。""",
    }

    def analyze(self, question: str, sql: str, result: dict, output_format: str = "table") -> dict:
        from app.core.llm import get_llm_client

        if result.get("error"):
            base = {"summary": f"查询出错：{result['error']}"}
            if output_format == "report":
                base.update({"title": "查询失败", "sections": [], "conclusion": "", "chart": None})
            elif output_format == "json":
                base.update({"data": [], "schema": {}})
            else:
                base.update({"highlights": [], "chart": None})
            return base

        if result.get("row_count", 0) == 0:
            base = {"summary": "查询结果为空，没有匹配的数据。"}
            if output_format == "report":
                base.update({"title": "无数据", "sections": [], "conclusion": "", "chart": None})
            elif output_format == "json":
                base.update({"data": [], "schema": {}})
            else:
                base.update({"highlights": [], "chart": None})
            return base

        # 构建预览（前 20 行）
        columns = result["columns"]
        rows = result["rows"][:20]
        preview_lines = ["| " + " | ".join(str(c) for c in columns) + " |"]
        preview_lines.append("|" + "---|" * len(columns))
        for row in rows:
            preview_lines.append("| " + " | ".join(str(v) for v in row) + " |")
        preview = "\n".join(preview_lines)

        client, model, cfg = get_llm_client()

        # 获取格式对应的 prompt
        format_prompt = self.FORMAT_PROMPTS.get(output_format, self.FORMAT_PROMPTS["table"])

        base_prompt = _get_sql_prompt("sql_analyze", "analyze")["system"]
        # 只取基础 prompt 中的部分（不含输出格式）
        base_parts = base_prompt.split("## 输出格式")
        prompt = base_parts[0].format(
            question=question, sql=sql, result_preview=preview
        ) + format_prompt

        _t0 = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=cfg.get("max_tokens", 2048),
            temperature=0.3,
        )
        logger.info(f"[SQL Analyze] LLM耗时 {time.time()-_t0:.1f}s, format={output_format}")

        content = (response.choices[0].message.content or "").strip()
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*$', '', content)

        try:
            parsed = json.loads(content)
            parsed["output_format"] = output_format
            return parsed
        except json.JSONDecodeError:
            base = {"summary": content, "output_format": output_format}
            if output_format == "report":
                base.update({"title": "分析结果", "sections": [], "conclusion": "", "chart": None})
            elif output_format == "json":
                base.update({"data": [], "schema": {}})
            else:
                base.update({"highlights": [], "chart": None})
            return base


# ═══════════════════════════════════════════════════
# SQL Agent 主类
# ═══════════════════════════════════════════════════

class SQLAgent:
    """一站式 SQL 分析引擎"""

    def __init__(self):
        self.schema = SchemaExtractor()
        self.generator = SQLGenerator()
        self.executor = SQLExecutor()
        self.analyzer = AnalysisGenerator()

    def query(self, question: str, history: list = None, output_format: str = "table", user_role: str = None) -> Generator[dict, None, None]:
        """
        流式输出，逐步返回：
        1. {"step": "sql", "data": {"sql": "...", "thinking": "..."}}
        2. {"step": "result", "data": {"columns": [...], "rows": [...], ...}}
        3. {"step": "analysis", "data": {"summary": "...", "chart": {...}, "output_format": "..."}}
        """
        _t_start = time.time()

        # Step 1: 获取 Schema
        schema_text = self.schema.get_schema_text()

        # Step 2: 生成 SQL
        _t = time.time()
        sql_info = self.generator.generate_with_retry(
            question, schema_text, self.executor, history
        )
        logger.info(f"[SQL Query] 生成SQL耗时 {time.time()-_t:.1f}s, attempts={sql_info.get('attempts',1)}")
        yield {"step": "sql", "data": sql_info}

        # Step 3: 执行
        _t = time.time()
        result = self.executor.execute(sql_info["sql"], user_role=user_role)
        logger.info(f"[SQL Query] 执行耗时 {time.time()-_t:.1f}s, rows={result.get('row_count',0)}")
        yield {"step": "result", "data": result}

        # Step 4: 分析
        _t = time.time()
        analysis = self.analyzer.analyze(question, sql_info["sql"], result, output_format=output_format)
        logger.info(f"[SQL Query] 分析耗时 {time.time()-_t:.1f}s")
        logger.info(f"[SQL Query] 总耗时 {time.time()-_t_start:.1f}s")
        yield {"step": "analysis", "data": analysis}

    def query_sync(self, question: str, user_role: str = None) -> str:
        """同步查询（供 Agent 工具调用），返回文本结果"""
        schema_text = self.schema.get_schema_text()

        sql_info = self.generator.generate_with_retry(
            question, schema_text, self.executor
        )

        result = self.executor.execute(sql_info["sql"], user_role=user_role)

        if result.get("error"):
            return f"查询出错：{result['error']}\n生成的 SQL：{sql_info['sql']}"

        # 构建文本结果
        columns = result["columns"]
        rows = result["rows"]
        lines = [f"SQL: {sql_info['sql']}\n"]
        lines.append(" | ".join(str(c) for c in columns))
        lines.append("-" * (len(lines[-1])))
        for row in rows[:50]:  # 最多返回 50 行
            lines.append(" | ".join(str(v) for v in row))

        if len(rows) > 50:
            lines.append(f"... 共 {len(rows)} 行，仅显示前 50 行")

        lines.append(f"\n耗时 {result['elapsed_ms']}ms")

        return "\n".join(lines)

    def execute_sql_direct(self, sql: str, user_role: str = None) -> dict:
        """直接执行 SQL（编辑后手动执行）"""
        return self.executor.execute(sql, user_role=user_role)


# 全局单例
_sql_agent = None

def get_sql_agent() -> SQLAgent:
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = SQLAgent()
    return _sql_agent

# 需要 Decimal 类型
from decimal import Decimal
