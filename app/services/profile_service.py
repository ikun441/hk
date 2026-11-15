from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select, update
from ..models import Profile, ProfileVersion, EvidenceUse, Message
from ..core import now
from ..auth import audit
from ..schemas import Proposal
from . import jungian_service

DIMS = ['Ne','Ni','Se','Si','Te','Ti','Fe','Fi']
EMPTY_BUSINESS = {'needs': [], 'purchase_stage': '', 'concerns': [], 'communication_preferences': [], 'objections': []}

def snapshot(profile):
    return {'business': deepcopy(profile.business), 'scores': deepcopy(profile.scores), 'field_meta': deepcopy(profile.field_meta)}

def initialize(db, customer_id, actor_id):
    p = Profile(customer_id=customer_id, version=0, business=deepcopy(EMPTY_BUSINESS), scores={k:50 for k in DIMS}, field_meta={})
    db.add(p)
    db.add(ProfileVersion(customer_id=customer_id, version=0, snapshot=snapshot(p) | {'score_delta':{k:0 for k in DIMS}}, actor_id=actor_id, reason='客户创建'))
    return p

def check_proposal(db, proposal: Proposal, customer_id):
    if proposal.customer_id != customer_id:
        raise HTTPException(422, '提案客户 ID 不一致')
    found = set(db.scalars(select(Message.id).where(Message.customer_id == customer_id, Message.id.in_(proposal.evidence_message_ids))))
    if found != set(proposal.evidence_message_ids):
        raise HTTPException(422, '证据消息不存在或属于其他客户')
    jungian_service.validate_analysis(db, proposal, customer_id)
    jungian_service.attach_context(db, db.get(Profile, customer_id), proposal)
    return proposal.model_dump()

def update_atomic(db, profile, expected, data):
    changed = db.execute(update(Profile).where(Profile.customer_id == profile.customer_id, Profile.version == expected).values(version=expected+1, updated_at=now(), **data), execution_options={'synchronize_session': False})
    if changed.rowcount != 1:
        raise HTTPException(409, '画像版本冲突，请刷新并重新分析或审核')
    db.expire(profile)

def approve(db, user, change, proposal, expected):
    profile = db.get(Profile, change.customer_id)
    if expected != profile.version or change.base_version != profile.version:
        raise HTTPException(409, '画像版本冲突，请刷新并基于最新版本重新提交分析')
    data = check_proposal(db, proposal, change.customer_id)
    state = snapshot(profile)
    updates = proposal.business_profile_updates.model_dump(exclude_none=True)
    for key, value in updates.items():
        if value != state['business'].get(key):
            state['business'][key] = value
            state['field_meta'][key] = {'evidence_message_ids': proposal.evidence_message_ids, 'updated_at': now().isoformat()+'Z', 'source': change.source, 'request_id': change.id, 'summary': '；'.join(value) if isinstance(value,list) else value}
    effective, consumed, excluded = jungian_service.scoring_plan(db, change.customer_id, proposal, profile.scores)
    for key, delta in effective.items():
        state['scores'][key] += delta
    for mid in consumed:
        db.add(EvidenceUse(customer_id=change.customer_id, message_id=mid, request_id=change.id))
    if proposal.jungian_analysis:
        state['field_meta']['jungian'] = {
            'analysis': {k:v.model_dump() for k,v in proposal.jungian_analysis.items()},
            'guidance': proposal.jungian_guidance.model_dump() if proposal.jungian_guidance else None,
            'last_delta': effective, 'updated_at': now().isoformat()+'Z',
            'request_id':change.id, 'source':change.source,
            'excluded_evidence_message_ids':sorted(excluded)}
    elif any(proposal.jungian_updates.model_dump().values()):
        state['field_meta']['jungian'] = {'analysis':{}, 'guidance':None, 'last_delta':effective, 'source':change.source, 'request_id':change.id, 'updated_at':now().isoformat()+'Z', 'reasoning':proposal.reasoning_summary}
    if state['field_meta'].get('jungian', {}).get('guidance'):
        state['field_meta']['jungian']['guidance']['basis'] = 'approved_profile'
    update_atomic(db, profile, expected, state)
    db.add(ProfileVersion(customer_id=change.customer_id, version=expected+1, snapshot=state | {'score_delta':effective}, request_id=change.id, actor_id=user.id, reason='批准画像更新'))
    change.proposal = data
    change.applied_delta = effective
    change.status = 'approved'
    change.reviewed_by = user.id
    change.reviewed_at = now()
    audit(db, user, 'profile.approve', change.id, {'customer_id': change.customer_id, 'version': expected+1, 'applied_delta': effective, 'duplicate_evidence': bool(excluded), 'edited': data != change.original_proposal})
    return profile
