#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")"
umask 077
if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12
    uv pip install --python .venv/bin/python -r requirements-lock.txt
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
    .venv/bin/python -m pip install -r requirements-lock.txt
  else
    print '请安装 Python 3.12 或 uv，详见 README.md。'
    read '?按回车退出…'
    exit 1
  fi
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
if ! .venv/bin/python -c 'from app.db import init_db,SessionLocal; from app.models import User,Role; from sqlalchemy import select; init_db(); db=SessionLocal(); raise SystemExit(0 if db.scalar(select(User.id).where(User.roles.any(Role.name=="superadmin"))) else 1)'; then
  print '首次运行：请设置管理员临时密码，登录后需要修改。'
  .venv/bin/python scripts/manage.py init-admin
fi
print '服务即将启动。请查看下方地址并在浏览器打开；按 Ctrl+C 停止服务。'
.venv/bin/python run.py
