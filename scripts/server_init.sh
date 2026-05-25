#!/bin/bash
#
# 知识库项目 - 服务器一键初始化脚本
# 适用系统：Ubuntu 22.04（阿里云轻量应用服务器）
# 用法：买完服务器后 SSH 进去，执行：
#   bash server_init.sh
#
set -e

# ─── 颜色 ───────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step()  { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

# ─── 配置（按需修改）────────────────────────────
PROJECT_DIR="/opt/knowledge-base"
DB_NAME="knowledge_base"
DB_USER="kb_user"
DB_PASS=$(openssl rand -hex 12)  # 自动生成随机密码
MYSQL_ROOT_PASS=$(openssl rand -hex 12)
DOMAIN=""  # 填你的域名，没有就留空用 IP
APP_PORT=8000

step "1/8 系统更新"
apt update && apt upgrade -y
apt install -y curl wget git unzip software-properties-common ufw

step "2/8 安装 Python 3.12"
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.12 python3.12-venv python3.12-dev
# 设置 python3 默认指向 3.12
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
info "Python $(python3 --version)"

step "3/8 安装 MySQL"
apt install -y mysql-server

# 启动 MySQL
systemctl start mysql
systemctl enable mysql

# 设置 root 密码
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PASS}'; FLUSH PRIVILEGES;"

# 创建项目数据库和用户
mysql -uroot -p"${MYSQL_ROOT_PASS}" <<EOF
CREATE DATABASE IF NOT EXISTS ${DB_NAME} DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
EOF

info "MySQL 已安装 | root 密码: ${MYSQL_ROOT_PASS} | 项目用户: ${DB_USER} / ${DB_PASS}"

step "4/8 安装 Nginx"
apt install -y nginx
systemctl start nginx
systemctl enable nginx
info "Nginx 已安装"

step "5/8 拉取项目代码"
mkdir -p /opt
# ── 如果代码在 Git 仓库，取消下面这行注释 ──
# git clone https://github.com/你的用户名/knowledge-base.git ${PROJECT_DIR}
#
# ── 如果用 scp 上传，先在本地执行： ──
# scp -r ./knowledge-base root@服务器IP:/opt/knowledge-base
#
if [ ! -d "${PROJECT_DIR}" ]; then
    mkdir -p ${PROJECT_DIR}
    warn "项目目录已创建: ${PROJECT_DIR}"
    warn "请把代码上传到这个目录，然后重新运行此脚本的 5-8 步"
    warn "上传方式: scp -r ./knowledge-base/* root@本机IP:/opt/knowledge-base/"
    exit 0
fi

step "6/8 配置 Python 虚拟环境"
cd ${PROJECT_DIR}
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
info "依赖安装完成"

step "7/8 生成配置文件 .env"
JWT_SECRET=$(openssl rand -hex 32)

cat > ${PROJECT_DIR}/.env <<ENVEOF
# ─── 安全密钥 ───────────────────────────────
JWT_SECRET=${JWT_SECRET}

# ─── 数据库 ─────────────────────────────────
DB_TYPE=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_NAME=${DB_NAME}

# ─── 应用 ───────────────────────────────────
APP_ENV=production
CORS_ORIGINS=*

# ─── LLM 配置（请手动填写）──────────────────
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://api.xxx.com/v1
# OPENAI_MODEL=gpt-4o-mini
ENVEOF

chown -R root:root ${PROJECT_DIR}
chmod 600 ${PROJECT_DIR}/.env
info ".env 已生成（请手动填写 LLM API Key）"

# 初始化数据库
cd ${PROJECT_DIR}
source venv/bin/activate
python scripts/init_db.py 2>/dev/null || warn "init_db.py 跳过（可能需要先配置 LLM）"
python scripts/migrate_db.py 2>/dev/null || warn "migrate_db.py 跳过"
info "数据库初始化完成"

step "8/8 配置 Nginx + Systemd 服务"

# Systemd 服务文件
cat > /etc/systemd/system/knowledge-base.service <<SVCEOF
[Unit]
Description=Knowledge Base RAG Application
After=network.target mysql.service

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin"
ExecStart=${PROJECT_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${APP_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable knowledge-base
systemctl start knowledge-base
info "Systemd 服务已创建并启动"

# Nginx 配置
cat > /etc/nginx/sites-available/knowledge-base <<NGXEOF
server {
    listen 80;
    server_name ${DOMAIN:-_};

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE 流式输出支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
NGXEOF

# 启用站点
ln -sf /etc/nginx/sites-available/knowledge-base /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
info "Nginx 反向代理已配置"

# ─── 防火墙 ──────────────────────────────────────
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
info "防火墙已开启（开放 22/80/443）"

# ─── 完成 ────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🚀 部署完成！${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo "  访问地址:  http://$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo "  默认账号:  admin / admin123"
echo ""
echo -e "${YELLOW}  ⚠️  接下来你需要手动做的事：${NC}"
echo ""
echo "  1. 编辑 .env，填写 LLM API Key："
echo "     nano ${PROJECT_DIR}/.env"
echo ""
echo "  2. 重启服务让配置生效："
echo "     systemctl restart knowledge-base"
echo ""
echo "  3. 修改默认管理员密码（登录后在用户管理里改）"
echo ""
echo "  4. （可选）配置 HTTPS："
echo "     apt install -y certbot python3-certbot-nginx"
echo "     certbot --nginx -d 你的域名"
echo ""
echo "  ── 数据库信息（保存好）──"
echo "  MySQL root:  ${MYSQL_ROOT_PASS}"
echo "  项目用户:    ${DB_USER} / ${DB_PASS}"
echo ""
