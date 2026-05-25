#!/bin/bash
#
# 试用环境定期重置脚本
# 功能：备份当前数据 → 恢复到干净状态 → 清理上传文件
# 建议 cron：每周一凌晨 3 点执行
#   crontab -e → 0 3 * * 1 /opt/knowledge-base/scripts/trial_reset.sh
#

set -e

PROJECT_DIR="/opt/knowledge-base"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_NAME="knowledge_base"
DB_USER="kb_user"
DB_PASS=""  # 填入你的数据库密码，或从 .env 读取

# 从 .env 读取数据库密码
if [ -f "${PROJECT_DIR}/.env" ]; then
    DB_PASS=$(grep '^DB_PASS=' "${PROJECT_DIR}/.env" | cut -d= -f2)
fi

MYSQL_CMD="mysql -u${DB_USER} -p${DB_PASS} ${DB_NAME}"
DUMP_CMD="mysqldump -u${DB_USER} -p${DB_PASS}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "[1/4] 备份当前数据..."
$DUMP_CMD --single-transaction $DB_NAME | gzip > "${BACKUP_DIR}/pre_reset_${TIMESTAMP}.sql.gz"
echo "  → ${BACKUP_DIR}/pre_reset_${TIMESTAMP}.sql.gz"

echo "[2/4] 清空用户数据（保留管理员）..."
$MYSQL_CMD <<'SQL'
-- 删除非管理员的对话和消息
DELETE FROM message WHERE conv_id IN (
    SELECT id FROM conversation WHERE user_id NOT IN (
        SELECT id FROM user WHERE role = 'super_admin'
    )
);
DELETE FROM conversation WHERE user_id NOT IN (
    SELECT id FROM user WHERE role = 'super_admin'
);

-- 删除非管理员用户
DELETE FROM user WHERE role != 'super_admin';

-- 清空用户记忆
DELETE FROM user_memory;

-- 清空 FAQ 候选
DELETE FROM FAQ_candidate;
DELETE FROM faq WHERE status = 'auto';

-- 清空审计日志（保留最近 7 天）
DELETE FROM query_audit_log WHERE created_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
SQL

echo "[3/4] 清理上传文件..."
# 清理 7 天前的上传文件
if [ -d "${PROJECT_DIR}/data/uploads" ]; then
    find "${PROJECT_DIR}/data/uploads" -type f -mtime +7 -delete 2>/dev/null || true
    echo "  → 已清理 7 天前的上传文件"
fi

echo "[4/4] 清理旧备份（保留最近 10 个）..."
cd "$BACKUP_DIR"
ls -t pre_reset_*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm --
echo "  → 已清理旧备份"

echo ""
echo "✅ 试用环境已重置"
echo "   备份文件: ${BACKUP_DIR}/pre_reset_${TIMESTAMP}.sql.gz"
