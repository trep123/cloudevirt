#!/usr/bin/env bash
# 本地一键启动：构建前端 → 部署到 nginx → 启动后端与节点 Agent
#
# 用法：
#   CLOUDVIRT_AGENT_TOKEN=xxx ./scripts/serve_local.sh
#
# 说明：仅用于开发/演示环境；生产请使用 deploy/systemd 下的 unit 与正式的
# nginx 站点配置（deploy/nginx/cloudvirt.conf）。
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${0}")/.." && pwd)
WEB_ROOT=${WEB_ROOT:-/var/www/cloudvirt}
NGINX_SITE=${NGINX_SITE:-/etc/nginx/sites-available/cloudvirt}
VENV=${VENV:-$ROOT_DIR/.venv}
BACKEND_DIR=$ROOT_DIR/apps/management
AGENT_DIR=$ROOT_DIR/services/virt-node-agent
DATABASE_URL=${DATABASE_URL:-postgresql://cloudvirt:cloudvirt-dev@127.0.0.1:5432/cloudvirt}
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')}
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-127.0.0.1,localhost}
DJANGO_CSRF_TRUSTED_ORIGINS=${DJANGO_CSRF_TRUSTED_ORIGINS:-http://127.0.0.1,http://localhost}

echo "==> 构建前端"
cd "$ROOT_DIR/frontend"
npm run build >/dev/null

echo "==> 部署静态文件到 $WEB_ROOT"
mkdir -p "$WEB_ROOT"
rm -rf "${WEB_ROOT:?}"/*
cp -r dist/* "$WEB_ROOT/"

echo "==> 安装 nginx 站点配置"
ln -sf "$ROOT_DIR/deploy/nginx/cloudvirt.conf" "$NGINX_SITE"
ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/cloudvirt
rm -f /etc/nginx/sites-enabled/default
nginx -t
nginx -s reload 2>/dev/null || nginx

echo "==> 启动后端（gunicorn 127.0.0.1:8000）"
cd "$BACKEND_DIR"
if ! curl -fsS -o /dev/null http://127.0.0.1:8000/api/v1/health 2>/dev/null; then
  DJANGO_DEBUG=false DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" DATABASE_URL="$DATABASE_URL" \
  DJANGO_ALLOWED_HOSTS="$DJANGO_ALLOWED_HOSTS" DJANGO_CSRF_TRUSTED_ORIGINS="$DJANGO_CSRF_TRUSTED_ORIGINS" \
    nohup "$VENV/bin/gunicorn" config.wsgi:application \
      --bind 127.0.0.1:8000 --workers 2 --threads 2 --timeout 60 \
      --pid /tmp/cloudvirt-gunicorn.pid \
      --access-logfile /tmp/cloudvirt-access.log \
      --error-logfile /tmp/cloudvirt-error.log --daemon
fi

if [ -n "${CLOUDVIRT_AGENT_TOKEN:-}" ]; then
  echo "==> 启动节点 Agent（127.0.0.1:9100）"
  cd "$AGENT_DIR"
  if ! curl -fsS -o /dev/null http://127.0.0.1:9100/health 2>/dev/null; then
    go build -o bin/virt-node-agent ./cmd/virt-node-agent
    CLOUDVIRT_AGENT_TOKEN="$CLOUDVIRT_AGENT_TOKEN" \
    CLOUDVIRT_IMAGE_DIR="${CLOUDVIRT_IMAGE_DIR:-/var/lib/cloudvirt/images}" \
    CLOUDVIRT_DISK_DIR="${CLOUDVIRT_DISK_DIR:-/var/lib/cloudvirt/disks}" \
      nohup ./bin/virt-node-agent >/tmp/cloudvirt-agent.log 2>&1 &
  fi
fi

sleep 2
echo
echo "前端: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)/"
echo "接口: http://127.0.0.1/api/v1/health -> $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1/api/v1/health)"
