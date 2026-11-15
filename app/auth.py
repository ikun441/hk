import hashlib
import secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, or_, false
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from .core import now, SESSION_HOURS
from .db import get_db
from .models import User, LoginSession, Customer, Assignment, Audit

hasher = PasswordHasher()

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def verify(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False

def audit(db, user, action, entity='', detail=None):
    db.add(Audit(user_id=user.id if user else None, action=action, entity=str(entity), detail=detail or {}))

def new_session(db, user):
    token = secrets.token_urlsafe(48)
    session = LoginSession(token_hash=digest(token), user_id=user.id, csrf=secrets.token_urlsafe(32), expires_at=now()+timedelta(hours=SESSION_HOURS))
    db.add(session)
    return token, session

def user_dict(user):
    return {k: getattr(user, k) for k in ['id','username','display_name','department_id','scope','active','must_change_password']} | {'role': user.role}

def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get('crm_session', '')
    session = db.get(LoginSession, digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, '请登录，会话可能已过期')
    user = db.get(User, session.user_id)
    if not user or not user.active or user.deleted:
        raise HTTPException(401, '账号已停用')
    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        csrf = request.headers.get('x-csrf-token', '')
        if not secrets.compare_digest(csrf, session.csrf):
            raise HTTPException(403, 'CSRF 校验失败，请刷新后重试')
    if user.must_change_password and request.url.path not in ['/api/auth/me','/api/auth/password','/api/auth/logout']:
        raise HTTPException(403, '首次登录必须修改密码')
    request.state.session = session
    return user

def writer(user):
    if user.role == 'readonly':
        raise HTTPException(403, '只读账号不能执行写操作')

def admin(user, super_only=False):
    allowed = ['superadmin'] if super_only else ['superadmin','admin']
    if user.role not in allowed:
        raise HTTPException(403, '需要管理员权限')

def customer_scope(user):
    if user.role == 'superadmin' or user.scope == 'all':
        return True
    explicit = Customer.id.in_(select(Assignment.customer_id).where(Assignment.user_id == user.id))
    if user.scope == 'department':
        dept = Customer.department_id == user.department_id if user.department_id else false()
        return or_(dept, explicit)
    if user.scope == 'own':
        return or_(Customer.owner_id == user.id, explicit)
    return explicit

def get_customer(db, user, customer_id, write=False):
    if write:
        writer(user)
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, customer_scope(user)))
    if not customer:
        raise HTTPException(404, '客户不存在或无权访问')
    if write and customer.archived:
        raise HTTPException(409, '客户已归档')
    return customer
