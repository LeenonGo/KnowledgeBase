#!/bin/bash
# 知识库项目 - 数据库备份与恢复脚本
# 用法:
#   ./scripts/db_backup_restore.sh backup          # 备份当前数据库
#   ./scripts/db_backup_restore.sh restore <文件>   # 从备份文件恢复
#   ./scripts/db_backup_restore.sh list             # 列出所有备份文件

set -e

# ─── 配置（按需修改）──────────────────────
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASS:-}"
DB_NAME="${DB_NAME:-knowledge_base}"
BACKUP_DIR="./backups"

# ─── 颜色 ─────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ─── MySQL 连接参数 ────────────────────────
MYSQL_CMD="mysql -h${DB_HOST} -P${DB_PORT} -u${DB_USER}"
DUMP_CMD="mysqldump -h${DB_HOST} -P${DB_PORT} -u${DB_USER}"
if [ -n "$DB_PASS" ]; then
    MYSQL_CMD="$MYSQL_CMD -p${DB_PASS}"
    DUMP_CMD="$DUMP_CMD -p${DB_PASS}"
fi

mkdir -p "$BACKUP_DIR"

# ─── 备份 ──────────────────────────────────
do_backup() {
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql"

    info "开始备份数据库: ${DB_NAME}"
    $DUMP_CMD --single-transaction --routines --triggers "$DB_NAME" > "$BACKUP_FILE"

    # 压缩
    gzip "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"

    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    info "备份完成: ${BACKUP_FILE} (${FILE_SIZE})"
}

# ─── 恢复 ──────────────────────────────────
do_restore() {
    RESTORE_FILE="$1"

    if [ -z "$RESTORE_FILE" ]; then
        error "请指定备份文件: $0 restore <backup_file.sql.gz>"
    fi

    if [ ! -f "$RESTORE_FILE" ]; then
        error "文件不存在: ${RESTORE_FILE}"
    fi

    # 确认
    warn "⚠️  这将覆盖数据库 '${DB_NAME}' 的所有数据！"
    read -p "确认恢复？(输入 yes 继续): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        info "已取消"
        exit 0
    fi

    # 先自动备份当前数据（防止误操作）
    SAFETY_FILE="${BACKUP_DIR}/${DB_NAME}_pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
    info "安全备份当前数据到: ${SAFETY_FILE}"
    $DUMP_CMD --single-transaction "$DB_NAME" | gzip > "$SAFETY_FILE"

    # 恢复
    info "开始恢复: ${RESTORE_FILE}"
    if [[ "$RESTORE_FILE" == *.gz ]]; then
        gunzip -c "$RESTORE_FILE" | $MYSQL_CMD "$DB_NAME"
    else
        $MYSQL_CMD "$DB_NAME" < "$RESTORE_FILE"
    fi

    info "恢复完成！（原数据已保存在 ${SAFETY_FILE}）"
}

# ─── 列出备份 ──────────────────────────────
do_list() {
    echo ""
    echo "📋 备份文件列表 (${BACKUP_DIR}/):"
    echo "─────────────────────────────────────────"
    if ls "$BACKUP_DIR"/*.sql.gz 1>/dev/null 2>&1; then
        ls -lh "$BACKUP_DIR"/*.sql.gz | awk '{print "  " $NF "  (" $5 ")"}'
    else
        echo "  （无备份文件）"
    fi
    echo ""
}

# ─── 主逻辑 ────────────────────────────────
case "$1" in
    backup)
        do_backup
        ;;
    restore)
        do_restore "$2"
        ;;
    list)
        do_list
        ;;
    *)
        echo "用法:"
        echo "  $0 backup            备份当前数据库"
        echo "  $0 restore <file>    从备份文件恢复（会先自动备份当前数据）"
        echo "  $0 list              列出所有备份"
        echo ""
        echo "环境变量:"
        echo "  DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME"
        exit 1
        ;;
esac
