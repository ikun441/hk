"""Local administrator commands; run from the project root."""
import argparse
import getpass
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from sqlalchemy import select, delete
from app.db import init_db, SessionLocal, engine
from app.models import User, Role, LoginSession
from app.auth import hasher, audit
from app.core import DATABASE_URL


def read_password(env_name):
    password=os.getenv(env_name) or getpass.getpass('密码（至少12位）: ')
    if len(password)<12 or len(password)>256:
        raise SystemExit('密码长度须为 12–256 位')
    return password


def main():
    parser=argparse.ArgumentParser(description='CRM 本地管理工具')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init-admin')
    init.add_argument('--username',default=os.getenv('ADMIN_USERNAME','admin'))
    reset=sub.add_parser('reset-password')
    reset.add_argument('username')
    backup=sub.add_parser('backup')
    backup.add_argument('path')
    restore=sub.add_parser('restore')
    restore.add_argument('path')
    restore.add_argument('--confirm-stopped',action='store_true')
    args=parser.parse_args()
    if args.command in ['backup','restore']:
        if not DATABASE_URL.startswith('sqlite:///') or ':memory:' in DATABASE_URL:
            raise SystemExit('该命令仅支持文件型 SQLite')
        db_path=Path(DATABASE_URL.removeprefix('sqlite:///')).resolve()
        other=Path(args.path).resolve()
        if db_path==other:
            raise SystemExit('备份文件不能与运行数据库相同')
        if args.command=='backup':
            if other.exists():
                raise SystemExit('目标文件已存在，请使用新文件名')
            other.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(f'file:{db_path}?mode=ro',uri=True) as source, sqlite3.connect(other) as target:
                source.backup(target)
            os.chmod(other,0o600)
            with SessionLocal.begin() as db:
                audit(db,None,'database.backup',other.name)
        else:
            if not args.confirm_stopped:
                raise SystemExit('先停止服务，再加 --confirm-stopped；恢复会覆盖当前数据库')
            if not other.is_file():
                raise SystemExit('备份文件不存在')
            with sqlite3.connect(f'file:{other}?mode=ro',uri=True) as source:
                if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise SystemExit('备份完整性校验失败')
                tables={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'users','customer_profiles','audit_logs','sessions'}.issubset(tables):
                    raise SystemExit('不是兼容的 CRM 备份')
                engine.dispose()
                with sqlite3.connect(db_path) as target:
                    source.backup(target)
            with SessionLocal.begin() as db:
                db.execute(delete(LoginSession))
                audit(db,None,'database.restore',other.name)
        print('完成：'+str(other))
        return
    init_db()
    with SessionLocal.begin() as db:
        user=db.scalar(select(User).where(User.username==args.username))
        if args.command=='init-admin':
            if db.scalar(select(User.id).where(User.roles.any(Role.name=='superadmin'))):
                raise SystemExit('已有超级管理员；请使用现有账号或 reset-password')
            if user:
                raise SystemExit('该用户名已存在')
            user=User(username=args.username,display_name='系统管理员',scope='all',password_hash=hasher.hash(read_password('ADMIN_PASSWORD')),roles=[db.get(Role,'superadmin')])
            db.add(user)
            db.flush()
            audit(db,user,'user.init_admin',user.id)
        else:
            if not user or user.deleted:
                raise SystemExit('账号不存在')
            user.password_hash=hasher.hash(read_password('RESET_PASSWORD'))
            user.must_change_password=True
            db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
            audit(db,None,'user.password_reset',user.id)
    print('完成，首次登录必须修改密码')

if __name__=='__main__':
    main()
