from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from ..db import get_db
from ..models import User, Department, Role, LoginSession, Customer, Audit, Setting
from ..schemas import UserIn, UserEdit, DepartmentIn, SettingsIn
from ..auth import current_user, admin, hasher, user_dict, audit
from ..services.ai_service import config_status
from ..core import SESSION_HOURS
from .common import page_query, serialize

router=APIRouter(prefix='/api/admin',tags=['系统管理'])

def check_user_scope(db,actor,role,scope,department_id,target=None):
    admin(actor)
    if department_id is not None and not db.get(Department,department_id):
        raise HTTPException(422,'部门不存在')
    if role=='admin' and (scope!='department' or not department_id):
        raise HTTPException(422,'管理员必须指定部门且范围为本部门')
    if role=='superadmin' and scope!='all':
        raise HTTPException(422,'超级管理员范围必须为全部')
    if scope=='department' and not department_id:
        raise HTTPException(422,'本部门范围必须指定部门')
    if actor.role!='superadmin':
        if not actor.department_id or role not in ['employee','readonly'] or scope not in ['own','department','assigned'] or department_id!=actor.department_id:
            raise HTTPException(403,'管理员仅能管理本部门员工和只读账号')
        if target and (target.department_id!=actor.department_id or target.role not in ['employee','readonly']):
            raise HTTPException(403,'不能管理该账号')

def target_user(db,actor,user_id):
    admin(actor)
    target=db.get(User,user_id)
    if not target or target.deleted:
        raise HTTPException(404,'账号不存在')
    if actor.role!='superadmin' and (not actor.department_id or target.department_id!=actor.department_id or target.role not in ['employee','readonly']):
        raise HTTPException(403,'不能管理该账号')
    return target

@router.get('/users')
def users(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    stmt=select(User).where(User.deleted.is_(False))
    if user.role!='superadmin':
        stmt=stmt.where(User.department_id==user.department_id)
    result=page_query(db,stmt.order_by(User.id),page,page_size)
    result['items']=[user_dict(u) for u in result['items']]
    return result

@router.post('/users',status_code=201)
def create_user(data:UserIn,user=Depends(current_user),db=Depends(get_db)):
    check_user_scope(db,user,data.role,data.scope,data.department_id)
    if db.scalar(select(User.id).where(User.username==data.username)):
        raise HTTPException(409,'用户名已存在')
    target=User(**data.model_dump(exclude={'password','role'}),password_hash=hasher.hash(data.password),roles=[db.get(Role,data.role)],must_change_password=True)
    db.add(target)
    db.flush()
    audit(db,user,'user.create',target.id,{'role':data.role,'scope':data.scope,'department_id':data.department_id})
    db.commit()
    return user_dict(target)

@router.put('/users/{user_id}')
def edit_user(user_id:int,data:UserEdit,user=Depends(current_user),db=Depends(get_db)):
    target=target_user(db,user,user_id)
    check_user_scope(db,user,data.role,data.scope,data.department_id,target)
    if target.id==user.id and (not data.active or data.role!=target.role or data.scope!=target.scope):
        raise HTTPException(409,'不能停用自身或降低自身权限，请由另一名超级管理员操作')
    before=user_dict(target)
    for key,value in data.model_dump(exclude={'role'}).items():
        setattr(target,key,value)
    target.roles=[db.get(Role,data.role)]
    db.execute(delete(LoginSession).where(LoginSession.user_id==target.id))
    audit(db,user,'user.permissions_changed',target.id,{'before':before,'after':user_dict(target)})
    db.commit()
    return user_dict(target)

@router.delete('/users/{user_id}')
def delete_user(user_id:int,user=Depends(current_user),db=Depends(get_db)):
    target=target_user(db,user,user_id)
    if target.id==user.id:
        raise HTTPException(409,'不能删除自身账号')
    target.active=False
    target.deleted=True
    db.execute(delete(LoginSession).where(LoginSession.user_id==target.id))
    audit(db,user,'user.delete',target.id,{'strategy':'soft_delete'})
    db.commit()
    return {'ok':True}

@router.get('/departments')
def departments(user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    stmt=select(Department)
    if user.role!='superadmin':
        stmt=stmt.where(Department.id==user.department_id)
    return [serialize(d,'id name created_at updated_at') for d in db.scalars(stmt.order_by(Department.id))]

@router.post('/departments',status_code=201)
def add_department(data:DepartmentIn,user=Depends(current_user),db=Depends(get_db)):
    admin(user,super_only=True)
    department=Department(**data.model_dump())
    db.add(department)
    db.flush()
    audit(db,user,'department.create',department.id)
    db.commit()
    return serialize(department,'id name')

@router.put('/departments/{department_id}')
def edit_department(department_id:int,data:DepartmentIn,user=Depends(current_user),db=Depends(get_db)):
    admin(user,super_only=True)
    department=db.get(Department,department_id)
    if not department:
        raise HTTPException(404,'部门不存在')
    department.name=data.name
    audit(db,user,'department.update',department_id)
    db.commit()
    return serialize(department,'id name')

@router.delete('/departments/{department_id}')
def delete_department(department_id:int,user=Depends(current_user),db=Depends(get_db)):
    admin(user,super_only=True)
    department=db.get(Department,department_id)
    if not department:
        raise HTTPException(404,'部门不存在')
    if db.scalar(select(User.id).where(User.department_id==department_id).limit(1)) or db.scalar(select(Customer.id).where(Customer.department_id==department_id).limit(1)):
        raise HTTPException(409,'部门仍关联账号或客户，请先调整归属')
    db.delete(department)
    audit(db,user,'department.delete',department_id)
    db.commit()
    return {'ok':True}

@router.get('/settings')
def settings(user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    company=db.get(Setting,'company_name')
    return {'company_name':company.value if company else '企业客户 CRM','ai':config_status(db),'session_hours':SESSION_HOURS}

@router.put('/settings')
def save_settings(data:SettingsIn,user=Depends(current_user),db=Depends(get_db)):
    admin(user,super_only=True)
    if data.external_ai_enabled and not data.data_policy.strip():
        raise HTTPException(422,'启用外发前必须填写数据处理规则')
    for key,value in data.model_dump().items():
        setting=db.get(Setting,key)
        if setting:
            setting.value=value
        else:
            db.add(Setting(key=key,value=value))
    audit(db,user,'settings.update',detail=data.model_dump())
    db.commit()
    return {'ok':True}

@router.get('/audits')
def audits(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    stmt=select(Audit)
    if user.role!='superadmin':
        stmt=stmt.where(Audit.user_id.in_(select(User.id).where(User.department_id==user.department_id)))
    result=page_query(db,stmt.order_by(Audit.id.desc()),page,page_size)
    result['items']=[serialize(a,'id user_id action entity detail created_at') for a in result['items']]
    return result
