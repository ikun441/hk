from datetime import timedelta
from collections import Counter
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, delete, func, or_
from openpyxl import Workbook
from ..db import get_db
from ..models import Customer, User, Department, Assignment, Message, Profile, ChangeRequest, Audit, ProfileVersion, EvidenceUse
from ..schemas import CustomerIn, MessageIn
from ..auth import current_user, writer, get_customer, customer_scope, audit
from ..core import now
from ..services import profile_service, import_service
from .common import serialize, page_query, CUSTOMER_FIELDS, MESSAGE_FIELDS

router=APIRouter(prefix='/api',tags=['客户与工作台'])

def customer_data(db,customer):
    owner=db.get(User,customer.owner_id)
    department=db.get(Department,customer.department_id) if customer.department_id else None
    return serialize(customer,CUSTOMER_FIELDS) | {'owner_name':owner.display_name if owner else '', 'department_name':department.name if department else '', 'authorized_user_ids':list(db.scalars(select(Assignment.user_id).where(Assignment.customer_id==customer.id)))}

def assign_customer(db,user,data,existing=None):
    owner_id=data.owner_id or (existing.owner_id if existing else user.id)
    owner=db.get(User,owner_id)
    if not owner or not owner.active or owner.deleted:
        raise HTTPException(422,'负责人不存在或已禁用')
    dept_id=data.department_id if data.department_id is not None else owner.department_id
    if dept_id and not db.get(Department,dept_id):
        raise HTTPException(422,'部门不存在')
    if user.role=='superadmin':
        pass
    elif user.role=='admin':
        if not user.department_id or owner.department_id!=user.department_id or dept_id!=user.department_id:
            raise HTTPException(403,'管理员只能分配本部门客户')
        if existing and set(data.authorized_user_ids)!=set(db.scalars(select(Assignment.user_id).where(Assignment.customer_id==existing.id))):
            raise HTTPException(403,'特定客户授权仅超级管理员可修改')
        if not existing and data.authorized_user_ids:
            raise HTTPException(403,'特定客户授权仅超级管理员可配置')
    else:
        if existing:
            original=customer_data(db,existing)
            if owner_id!=existing.owner_id or dept_id!=existing.department_id or set(data.authorized_user_ids)!=set(original['authorized_user_ids']):
                raise HTTPException(403,'员工不能修改客户归属和授权')
        elif owner_id!=user.id or dept_id!=user.department_id or data.authorized_user_ids or user.scope=='assigned':
            raise HTTPException(403,'不能创建未授权归属的客户')
    for uid in data.authorized_user_ids:
        target=db.get(User,uid)
        if not target or not target.active or target.deleted:
            raise HTTPException(422,f'授权账号 {uid} 不存在或已禁用')
    values=data.model_dump(exclude={'authorized_user_ids'})
    values.update(owner_id=owner_id,department_id=dept_id)
    return values

@router.get('/lookups')
def lookups(user=Depends(current_user),db=Depends(get_db)):
    users=select(User).where(User.active.is_(True),User.deleted.is_(False))
    if user.role!='superadmin':
        users=users.where(or_(User.department_id==user.department_id if user.department_id else User.id==user.id,User.id==user.id))
    depts=select(Department)
    if user.role!='superadmin':
        depts=depts.where(Department.id==user.department_id)
    return {'users':[{'id':u.id,'display_name':u.display_name,'department_id':u.department_id} for u in db.scalars(users)],'departments':[serialize(d,'id name') for d in db.scalars(depts)]}

@router.get('/dashboard')
def dashboard(user=Depends(current_user),db=Depends(get_db)):
    ids=select(Customer.id).where(customer_scope(user),Customer.archived.is_(False))
    total=db.scalar(select(func.count()).select_from(ids.subquery()))
    # Shanghai calendar day, independent of host timezone.
    today=(now()+timedelta(hours=8)).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(hours=8)
    new=db.scalar(select(func.count()).select_from(Customer).where(Customer.id.in_(ids),Customer.created_at>=today))
    pending=db.scalar(select(func.count()).select_from(ChangeRequest).where(ChangeRequest.customer_id.in_(ids),ChangeRequest.status=='pending'))
    todo=list(db.scalars(select(Customer).where(Customer.id.in_(ids),or_(Customer.last_followup_at.is_(None),Customer.last_followup_at<now()-timedelta(days=7))).order_by(Customer.last_followup_at).limit(8)))
    followups=db.scalar(select(func.count()).select_from(Customer).where(Customer.id.in_(ids),or_(Customer.last_followup_at.is_(None),Customer.last_followup_at<now()-timedelta(days=7))))
    activity=list(db.scalars(select(Customer).where(Customer.id.in_(ids)).order_by(Customer.updated_at.desc()).limit(8)))
    start=today-timedelta(days=13)
    end=today+timedelta(days=1)
    days=[(start+timedelta(hours=8,days=i)).date().isoformat() for i in range(14)]
    message_days=Counter((stamp+timedelta(hours=8)).date().isoformat() for stamp in db.scalars(
        select(Message.sent_at).where(Message.customer_id.in_(ids),Message.sent_at>=start,Message.sent_at<end)))
    customer_days=Counter((stamp+timedelta(hours=8)).date().isoformat() for stamp in db.scalars(
        select(Customer.created_at).where(Customer.id.in_(ids),Customer.created_at>=start,Customer.created_at<end)))
    statuses=dict(db.execute(select(Customer.status,func.count()).where(Customer.id.in_(ids)).group_by(Customer.status)).all())
    approvals=dict(db.execute(select(ChangeRequest.status,func.count()).where(ChangeRequest.customer_id.in_(ids)).group_by(ChangeRequest.status)).all())
    charts={'activity':[{'date':day,'messages':message_days[day],'new_customers':customer_days[day]} for day in days],
            'customer_status':{k:statuses.get(k,0) for k in ['potential','following','cooperating','closed']},
            'approval_status':{k:approvals.get(k,0) for k in ['pending','approved','rejected']},
            'message_total':db.scalar(select(func.count()).select_from(Message).where(Message.customer_id.in_(ids)))}
    return {'total_customers':total,'new_today':new,'pending_requests':pending,'followup_count':followups,'todos':[serialize(c,CUSTOMER_FIELDS) for c in todo],'activities':[serialize(c,CUSTOMER_FIELDS) for c in activity],'charts':charts}

@router.get('/customers')
def customers(q:str=Query('',max_length=200),industry:str=Query('',max_length=100),status:str='',owner_id:int|None=None,archived:bool=False,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    stmt=select(Customer).where(customer_scope(user),Customer.archived==archived)
    if q:
        escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        stmt=stmt.where(Customer.name.ilike('%'+escaped+'%',escape='\\'))
    if industry:
        stmt=stmt.where(Customer.industry==industry)
    if status:
        stmt=stmt.where(Customer.status==status)
    if owner_id:
        stmt=stmt.where(Customer.owner_id==owner_id)
    result=page_query(db,stmt.order_by(Customer.updated_at.desc(),Customer.id.desc()),page,page_size)
    result['items']=[customer_data(db,c) for c in result['items']]
    return result

@router.get('/customers/export')
def export(user=Depends(current_user),db=Depends(get_db)):
    book=Workbook()
    sheet=book.active
    sheet.append(['客户ID','企业名称','行业','联系人','联系方式','状态','负责人ID','部门ID'])
    for c in db.scalars(select(Customer).where(customer_scope(user))):
        sheet.append([c.id,c.name,c.industry,c.contact,c.contact_info,c.status,c.owner_id,c.department_id])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value,str):
                cell.data_type='s'
    stream=BytesIO()
    book.save(stream)
    audit(db,user,'customer.export')
    db.commit()
    return Response(stream.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=customers.xlsx'})

@router.post('/customers',status_code=201)
def create(data:CustomerIn,user=Depends(current_user),db=Depends(get_db)):
    writer(user)
    values=assign_customer(db,user,data)
    c=Customer(**values)
    db.add(c)
    db.flush()
    for uid in set(data.authorized_user_ids):
        db.add(Assignment(user_id=uid,customer_id=c.id))
    profile_service.initialize(db,c.id,user.id)
    audit(db,user,'customer.create',c.id)
    db.commit()
    return customer_data(db,c)

@router.get('/customers/{customer_id}')
def detail(customer_id:int,user=Depends(current_user),db=Depends(get_db)):
    return customer_data(db,get_customer(db,user,customer_id))

@router.put('/customers/{customer_id}')
def edit(customer_id:int,data:CustomerIn,user=Depends(current_user),db=Depends(get_db)):
    c=get_customer(db,user,customer_id,write=True)
    values=assign_customer(db,user,data,c)
    before={'owner_id':c.owner_id,'department_id':c.department_id,'authorized_user_ids':customer_data(db,c)['authorized_user_ids']}
    for key,value in values.items():
        setattr(c,key,value)
    if user.role=='superadmin':
        db.execute(delete(Assignment).where(Assignment.customer_id==c.id))
        for uid in set(data.authorized_user_ids):
            db.add(Assignment(user_id=uid,customer_id=c.id))
    audit(db,user,'customer.update',c.id,{'previous_assignment':before,'new_assignment':{'owner_id':c.owner_id,'department_id':c.department_id,'authorized_user_ids':data.authorized_user_ids}})
    db.commit()
    return customer_data(db,c)

@router.delete('/customers/{customer_id}')
def archive(customer_id:int,user=Depends(current_user),db=Depends(get_db)):
    c=get_customer(db,user,customer_id,write=True)
    c.archived=True
    audit(db,user,'customer.archive',c.id)
    db.commit()
    return {'ok':True}

@router.get('/customers/{customer_id}/messages')
def messages(customer_id:int,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    get_customer(db,user,customer_id)
    result=page_query(db,select(Message).where(Message.customer_id==customer_id).order_by(Message.sent_at.desc(),Message.id.desc()),page,page_size)
    result['items']=[serialize(m,MESSAGE_FIELDS) for m in result['items']]
    return result

@router.post('/customers/{customer_id}/messages',status_code=201)
def add_message(customer_id:int,data:MessageIn,user=Depends(current_user),db=Depends(get_db)):
    c=get_customer(db,user,customer_id,write=True)
    message=import_service.insert_message(db,c,user,data)
    audit(db,user,'message.add',c.id,{'duplicate':message is None})
    db.commit()
    return {'duplicate':message is None,'message':serialize(message,MESSAGE_FIELDS) if message else None}

@router.get('/workspace')
def workspace(user=Depends(current_user),db=Depends(get_db)):
    from ..models import Setting
    from ..services.ai_service import config_status
    company=db.get(Setting,'company_name')
    cfg=config_status(db)
    return {'company_name':company.value if company else '企业客户 CRM','ai_mode':cfg['mode'],'external_ai_enabled':cfg['external_ai_enabled'],'data_policy':cfg['data_policy']}


@router.get('/customers/{customer_id}/insights')
def customer_insights(customer_id:int,user=Depends(current_user),db=Depends(get_db)):
    get_customer(db,user,customer_id)
    counts=dict(db.execute(select(ChangeRequest.status,func.count()).where(ChangeRequest.customer_id==customer_id).group_by(ChangeRequest.status)).all())
    messages=dict(db.execute(select(Message.speaker,func.count()).where(Message.customer_id==customer_id).group_by(Message.speaker)).all())
    versions=list(db.scalars(select(ProfileVersion).where(ProfileVersion.customer_id==customer_id).order_by(ProfileVersion.version.desc()).limit(30)))
    return {'message_count':sum(messages.values()),'message_speakers':{key:messages.get(key,0) for key in ['customer','employee']},
            'counted_evidence':db.scalar(select(func.count()).select_from(EvidenceUse).where(EvidenceUse.customer_id==customer_id)),
            'request_status':{key:counts.get(key,0) for key in ['pending','approved','rejected']},
            'version_total':db.scalar(select(func.count()).select_from(ProfileVersion).where(ProfileVersion.customer_id==customer_id)),
            'versions':[{'version':v.version,'created_at':v.created_at.isoformat()+'Z','scores':v.snapshot['scores'],'delta':v.snapshot.get('score_delta',{}),'reason':v.reason} for v in reversed(versions)]}
