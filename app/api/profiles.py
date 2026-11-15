from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from ..db import get_db
from ..models import Profile, ProfileVersion, ChangeRequest, Customer, Message, Feedback
from ..schemas import AnalyzeIn, ReviewIn, RestoreIn, FeedbackIn
from ..auth import current_user, get_customer, customer_scope, admin, writer, audit
from ..core import now
from ..services import ai_service, profile_service
from .common import serialize, page_query, REQUEST_FIELDS, MESSAGE_FIELDS

router=APIRouter(prefix='/api',tags=['画像与审核'])

def request_detail(db,user,change):
    customer=get_customer(db,user,change.customer_id)
    evidence=list(db.scalars(select(Message).where(Message.customer_id==customer.id,Message.id.in_(change.proposal['evidence_message_ids'])).order_by(Message.sent_at)))
    return serialize(change,REQUEST_FIELDS)|{'customer_name':customer.name,'evidence':[serialize(m,MESSAGE_FIELDS) for m in evidence], 'current_profile':profile_service.snapshot(db.get(Profile,customer.id)), 'current_version':db.get(Profile,customer.id).version}

@router.get('/customers/{customer_id}/profile')
def get_profile(customer_id:int,user=Depends(current_user),db=Depends(get_db)):
    get_customer(db,user,customer_id)
    p=db.get(Profile,customer_id)
    return profile_service.snapshot(p)|{'customer_id':customer_id,'version':p.version,'updated_at':p.updated_at.isoformat()+'Z'}

@router.post('/customers/{customer_id}/analyze',status_code=201)
def analyze(customer_id:int,data:AnalyzeIn,user=Depends(current_user),db=Depends(get_db)):
    customer=get_customer(db,user,customer_id,write=True)
    profile=db.get(Profile,customer_id)
    base_version=profile.version
    if data.manual_proposal:
        proposal=data.manual_proposal
        source='manual'
    else:
        stmt=select(Message).where(Message.customer_id==customer_id)
        if data.evidence_message_ids:
            stmt=stmt.where(Message.id.in_(data.evidence_message_ids))
        messages=list(db.scalars(stmt.order_by(Message.sent_at.desc(),Message.id.desc()).limit(100)))
        if not messages:
            raise HTTPException(422,'请先添加聊天消息')
        if data.evidence_message_ids and {m.id for m in messages}!=set(data.evidence_message_ids):
            raise HTTPException(422,'选择的证据不属于当前客户或不存在')
        proposal,source=ai_service.analyze(db,customer,profile,messages,data.external_consent)
    proposal_data=profile_service.check_proposal(db,proposal,customer_id)
    if source=='manual':
        messages=list(db.scalars(select(Message).where(Message.id.in_(proposal.evidence_message_ids))))
        proposal=ai_service.protect_refusal(proposal,messages)
        proposal_data=proposal.model_dump()
    change=ChangeRequest(customer_id=customer_id,submitted_by=user.id,base_version=base_version,proposal=proposal_data,original_proposal=proposal_data,source=source)
    db.add(change)
    db.flush()
    audit(db,user,'profile.submit',change.id,{'customer_id':customer_id,'source':source,'base_version':base_version})
    db.commit()
    return request_detail(db,user,change)

@router.get('/requests')
def requests(status:str='pending',customer_id:int|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    ids=select(Customer.id).where(customer_scope(user))
    stmt=select(ChangeRequest).where(ChangeRequest.customer_id.in_(ids))
    if status and status!='all':
        stmt=stmt.where(ChangeRequest.status==status)
    if customer_id:
        get_customer(db,user,customer_id)
        stmt=stmt.where(ChangeRequest.customer_id==customer_id)
    result=page_query(db,stmt.order_by(ChangeRequest.created_at.desc(),ChangeRequest.id.desc()),page,page_size)
    result['items']=[serialize(r,REQUEST_FIELDS)|{'customer_name':db.get(Customer,r.customer_id).name} for r in result['items']]
    return result

@router.get('/requests/{request_id}')
def get_request(request_id:int,user=Depends(current_user),db=Depends(get_db)):
    change=db.get(ChangeRequest,request_id)
    if not change:
        raise HTTPException(404,'申请不存在')
    return request_detail(db,user,change)

@router.post('/requests/{request_id}/review')
def review(request_id:int,data:ReviewIn,user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    change=db.get(ChangeRequest,request_id)
    if not change:
        raise HTTPException(404,'申请不存在')
    get_customer(db,user,change.customer_id,write=data.action=='approve')
    claim=db.execute(update(ChangeRequest).where(ChangeRequest.id==request_id,ChangeRequest.status=='pending').values(status='processing'),execution_options={'synchronize_session':False})
    if claim.rowcount!=1:
        raise HTTPException(409,'该申请已经审核或正在处理中')
    change.review_note=data.note
    if data.action=='reject':
        change.status='rejected'
        change.reviewed_by=user.id
        change.reviewed_at=now()
        audit(db,user,'profile.reject',change.id,{'note':data.note})
    else:
        from ..schemas import Proposal
        proposal=data.edited_proposal or Proposal.model_validate(change.proposal)
        # Approval edits retain the same evidence boundary checks and refusal protection.
        profile_service.check_proposal(db,proposal,change.customer_id)
        messages=list(db.scalars(select(Message).where(Message.id.in_(proposal.evidence_message_ids))))
        proposal=ai_service.protect_refusal(proposal,messages)
        profile_service.approve(db,user,change,proposal,data.expected_version)
    db.commit()
    return request_detail(db,user,change)

@router.get('/customers/{customer_id}/versions')
def versions(customer_id:int,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(current_user),db=Depends(get_db)):
    get_customer(db,user,customer_id)
    result=page_query(db,select(ProfileVersion).where(ProfileVersion.customer_id==customer_id).order_by(ProfileVersion.version.desc()),page,page_size)
    result['items']=[serialize(v,'id customer_id version snapshot request_id actor_id reason created_at') for v in result['items']]
    return result

@router.post('/customers/{customer_id}/restore')
def restore(customer_id:int,data:RestoreIn,user=Depends(current_user),db=Depends(get_db)):
    admin(user)
    get_customer(db,user,customer_id,write=True)
    version=db.scalar(select(ProfileVersion).where(ProfileVersion.customer_id==customer_id,ProfileVersion.version==data.version))
    if not version:
        raise HTTPException(404,'历史版本不存在')
    profile=db.get(Profile,customer_id)
    state={key:version.snapshot[key] for key in ['business','scores','field_meta']}
    score_delta={key:state['scores'][key]-profile.scores[key] for key in profile_service.DIMS}
    profile_service.update_atomic(db,profile,data.expected_version,state)
    db.add(ProfileVersion(customer_id=customer_id,version=data.expected_version+1,snapshot=state | {'score_delta':score_delta},actor_id=user.id,reason=f'恢复至 v{data.version}：{data.reason}'))
    audit(db,user,'profile.restore',customer_id,{'from_version':data.version,'new_version':data.expected_version+1,'reason':data.reason})
    db.commit()
    return {'version':profile.version,**profile_service.snapshot(profile)}

@router.post('/requests/{request_id}/feedback')
def feedback(request_id:int,data:FeedbackIn,user=Depends(current_user),db=Depends(get_db)):
    writer(user)
    change=db.get(ChangeRequest,request_id)
    if not change:
        raise HTTPException(404,'申请不存在')
    get_customer(db,user,change.customer_id,write=True)
    record=db.get(Feedback,(request_id,user.id))
    if record:
        record.useful=data.useful
        record.note=data.note
    else:
        db.add(Feedback(request_id=request_id,user_id=user.id,**data.model_dump()))
    audit(db,user,'suggestion.feedback',request_id,{'useful':data.useful})
    db.commit()
    return {'ok':True}
