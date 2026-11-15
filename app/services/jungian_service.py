"""Evidence-bound exploratory expression references, never personality diagnoses."""
from sqlalchemy import select
from fastapi import HTTPException
from ..models import EvidenceUse, Message, Customer
from ..schemas import JungianContext

DIMS = ('Ne', 'Ni', 'Se', 'Si', 'Te', 'Ti', 'Fe', 'Fi')
# These are transparent product heuristics for expression style, not validated measurements.
STYLE_RULES = {
    'Ne': '明确要求多个新方案、备选可能性：先给少量可选方向',
    'Ni': '明确要求长期方向、整体脉络：先给整体摘要再说明路径',
    'Se': '明确要求现场实例、可见实际细节：用具体案例说明',
    'Si': '明确引用既往经验、固定流程或交接细节：说明步骤和前后衔接',
    'Te': '明确要求表格、清单、责任、时限、可执行结果：用结构化对照和行动清单',
    'Ti': '明确要求原理、定义、比较依据或逻辑解释：解释依据和边界',
    'Fe': '明确要求团队协调、照顾沟通对象、共同确认：说明协作及确认安排',
    'Fi': '明确表达个人价值取舍、自主决定的偏好：尊重其选择并保留决定空间',
}


def used_ids(db, customer_id):
    return set(db.scalars(select(EvidenceUse.message_id).where(EvidenceUse.customer_id == customer_id)))


def validate_analysis(db, proposal, customer_id):
    messages = {m.id: m for m in db.scalars(select(Message).where(
        Message.customer_id == customer_id, Message.id.in_(proposal.evidence_message_ids)))}
    customer = db.get(Customer, customer_id)
    from .ai_service import mask_value
    secrets = [customer.name, customer.contact, customer.contact_info]
    for dim, assessment in proposal.jungian_analysis.items():
        if proposal.jungian_updates.model_dump()[dim] and (
            assessment.confidence == 'insufficient' or not assessment.evidence or not assessment.reasoning.strip()
        ):
            raise HTTPException(422, f'{dim} 非零增量必须有客户原文和有效线索说明')
        for evidence in assessment.evidence:
            message = messages.get(evidence.message_id)
            if not message or message.speaker != 'customer':
                raise HTTPException(422, f'{dim} 证据必须是当前客户的发言，不能引用员工')
            normalized = mask_value(message.content, secrets)
            if evidence.quote not in message.content and evidence.quote not in normalized:
                raise HTTPException(422, f'{dim} 引文与消息 #{message.id} 原文不符')
    if proposal.jungian_analysis:
        for dim, delta in proposal.jungian_updates.model_dump().items():
            if delta and dim not in proposal.jungian_analysis:
                raise HTTPException(422, f'{dim} 缺少逐维分析')
    if proposal.jungian_guidance:
        for dim in proposal.jungian_guidance.dimensions:
            assessment = proposal.jungian_analysis.get(dim)
            if not assessment or assessment.confidence == 'insufficient' or not assessment.evidence or not assessment.reasoning.strip():
                raise HTTPException(422, f'话术参考维度 {dim} 缺少原文依据')


def scoring_plan(db, customer_id, proposal, scores):
    used = used_ids(db, customer_id)
    proposed = proposal.jungian_updates.model_dump()
    effective = dict.fromkeys(DIMS, 0)
    consumed = set()
    excluded = set()
    for dim, delta in proposed.items():
        if not delta:
            continue
        assessment = proposal.jungian_analysis.get(dim)
        support = {e.message_id for e in assessment.evidence} if assessment else set(proposal.evidence_message_ids)
        excluded.update(support & used)
        fresh = support - used
        # Legacy manual requests have aggregate evidence, so retain conservative deduplication.
        if not assessment and support & used:
            continue
        if fresh:
            effective[dim] = max(0, min(100, scores[dim] + delta)) - scores[dim]
            # Record evidence even when a bound suppresses movement, to prevent replay after restore.
            consumed.update(fresh)
    return effective, consumed, excluded


def attach_context(db, profile, proposal):
    delta, _, excluded = scoring_plan(db, profile.customer_id, proposal, profile.scores)
    proposal.jungian_context = JungianContext(
        profile_version=profile.version, current_scores=profile.scores,
        effective_deltas=delta, projected_scores={k: profile.scores[k]+delta[k] for k in DIMS},
        excluded_evidence_message_ids=sorted(excluded))
    if proposal.jungian_guidance:
        proposal.jungian_guidance.basis = (
            'proposal_preview' if any(delta.values()) else
            'approved_profile' if any(v != 50 for v in profile.scores.values()) else
            'evidence_only' if proposal.jungian_guidance.dimensions else 'insufficient')
    return proposal
