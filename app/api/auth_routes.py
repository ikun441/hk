from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, delete, func
from ..db import get_db
from ..models import User, LoginSession, LoginAttempt
from ..schemas import LoginIn, PasswordIn
from ..auth import current_user, digest, verify, hasher, new_session, user_dict, audit
from ..core import now, COOKIE_SECURE, SESSION_HOURS

router=APIRouter(prefix='/api/auth',tags=['认证'])

@router.post('/login')
def login(data:LoginIn, request:Request, response:Response, db=Depends(get_db)):
    key=digest((request.client.host if request.client else '')+'|'+data.username.lower())
    cutoff=now()-timedelta(minutes=15)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at<cutoff))
    count=db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key==key))
    if count>=10:
        raise HTTPException(429,'登录失败次数过多，请 15 分钟后重试')
    user=db.scalar(select(User).where(User.username==data.username))
    valid=verify(data.password,user.password_hash) if user else verify(data.password, hasher.hash('constant-time-placeholder'))
    if not user or not valid or not user.active or user.deleted:
        db.add(LoginAttempt(key=key))
        audit(db,user,'auth.login_failed',detail={'username':data.username})
        db.commit()
        raise HTTPException(401,'用户名或密码错误，或账号已停用')
    db.execute(delete(LoginAttempt).where(LoginAttempt.key==key))
    db.execute(delete(LoginSession).where(LoginSession.expires_at<now()))
    token,session=new_session(db,user)
    audit(db,user,'auth.login')
    db.commit()
    response.set_cookie('crm_session',token,max_age=SESSION_HOURS*3600,httponly=True,secure=COOKIE_SECURE,samesite='strict',path='/')
    return {'user':user_dict(user),'csrf_token':session.csrf}

@router.get('/me')
def me(request:Request,user=Depends(current_user)):
    return {'user':user_dict(user),'csrf_token':request.state.session.csrf}

@router.post('/logout')
def logout(request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    db.delete(request.state.session)
    audit(db,user,'auth.logout')
    db.commit()
    response.delete_cookie('crm_session',path='/')
    return {'ok':True}

@router.post('/password')
def password(data:PasswordIn,response:Response,user=Depends(current_user),db=Depends(get_db)):
    if not verify(data.old_password,user.password_hash):
        raise HTTPException(400,'原密码不正确')
    if data.old_password==data.new_password:
        raise HTTPException(422,'新密码不能与原密码相同')
    user.password_hash=hasher.hash(data.new_password)
    user.must_change_password=False
    db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    audit(db,user,'auth.password_changed')
    db.commit()
    response.delete_cookie('crm_session',path='/')
    return {'ok':True,'message':'密码已修改，请重新登录'}
