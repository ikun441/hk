from datetime import datetime, timezone
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator, StringConstraints

PasswordText = Annotated[str, StringConstraints(strip_whitespace=False)]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=80)
    password: PasswordText = Field(min_length=1, max_length=256)

class PasswordIn(Strict):
    old_password: PasswordText = Field(min_length=1, max_length=256)
    new_password: PasswordText = Field(min_length=12, max_length=256)

class UserIn(Strict):
    username: str = Field(min_length=2, max_length=80, pattern=r'^[a-zA-Z0-9_.@-]+$')
    display_name: str = Field(min_length=1, max_length=100)
    password: PasswordText = Field(min_length=12, max_length=256)
    role: Literal['superadmin', 'admin', 'employee', 'readonly'] = 'employee'
    scope: Literal['all', 'department', 'own', 'assigned'] = 'own'
    department_id: int | None = None

class UserEdit(Strict):
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal['superadmin', 'admin', 'employee', 'readonly']
    scope: Literal['all', 'department', 'own', 'assigned']
    department_id: int | None = None
    active: bool = True

class DepartmentIn(Strict):
    name: str = Field(min_length=1, max_length=100)

class CustomerIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default='', max_length=100)
    contact: str = Field(default='', max_length=100)
    contact_info: str = Field(default='', max_length=200)
    source: str = Field(default='', max_length=100)
    owner_id: int | None = None
    department_id: int | None = None
    status: Literal['potential', 'following', 'cooperating', 'closed'] = 'potential'
    last_followup_at: datetime | None = None
    notes: str = Field(default='', max_length=10000)
    authorized_user_ids: list[int] = Field(default_factory=list, max_length=200)

    @field_validator('last_followup_at')
    @classmethod
    def normalize_time(cls, v):
        if v and v.tzinfo:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

class MessageIn(Strict):
    speaker: Literal['customer', 'employee']
    sent_at: datetime
    content: str = Field(min_length=1, max_length=20000)
    source: str = Field(default='manual', min_length=1, max_length=200)

    @field_validator('sent_at')
    @classmethod
    def normalize_time(cls, v):
        if v.tzinfo is None:
            raise ValueError('消息时间必须含时区，例如 +08:00')
        return v.astimezone(timezone.utc).replace(tzinfo=None)

class BusinessUpdates(Strict):
    needs: list[str] | None = Field(default=None, max_length=20)
    purchase_stage: str | None = Field(default=None, max_length=200)
    concerns: list[str] | None = Field(default=None, max_length=20)
    communication_preferences: list[str] | None = Field(default=None, max_length=20)
    objections: list[str] | None = Field(default=None, max_length=20)

    @field_validator('needs', 'concerns', 'communication_preferences', 'objections')
    @classmethod
    def length_items(cls, values):
        if values is not None and any(not x.strip() or len(x) > 500 for x in values):
            raise ValueError('画像条目须为 1–500 字')
        return values

class JungianUpdates(Strict):
    Ne: int = Field(default=0, ge=-10, le=10, strict=True)
    Ni: int = Field(default=0, ge=-10, le=10, strict=True)
    Se: int = Field(default=0, ge=-10, le=10, strict=True)
    Si: int = Field(default=0, ge=-10, le=10, strict=True)
    Te: int = Field(default=0, ge=-10, le=10, strict=True)
    Ti: int = Field(default=0, ge=-10, le=10, strict=True)
    Fe: int = Field(default=0, ge=-10, le=10, strict=True)
    Fi: int = Field(default=0, ge=-10, le=10, strict=True)

Dimension = Literal['Ne', 'Ni', 'Se', 'Si', 'Te', 'Ti', 'Fe', 'Fi']

class JungianEvidence(Strict):
    message_id: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=500)

class JungianAssessment(Strict):
    confidence: Literal['insufficient', 'low', 'medium'] = 'insufficient'
    evidence: list[JungianEvidence] = Field(default_factory=list, max_length=10)
    reasoning: str = Field(default='', max_length=1500)
    expression_tip: str = Field(default='', max_length=1000)

class JungianGuidance(Strict):
    summary: str = Field(min_length=1, max_length=2000)
    dimensions: list[Dimension] = Field(default_factory=list, max_length=8)
    wording_tips: list[str] = Field(default_factory=list, max_length=8)
    basis: Literal['approved_profile', 'proposal_preview', 'evidence_only', 'insufficient'] = 'insufficient'

class JungianContext(Strict):
    profile_version: int = Field(ge=0)
    current_scores: dict[Dimension, int]
    effective_deltas: dict[Dimension, int]
    projected_scores: dict[Dimension, int]
    excluded_evidence_message_ids: list[int] = Field(default_factory=list)

class Proposal(Strict):
    customer_id: int
    evidence_message_ids: list[int] = Field(min_length=1, max_length=100)
    business_profile_updates: BusinessUpdates = Field(default_factory=BusinessUpdates)
    jungian_updates: JungianUpdates = Field(default_factory=JungianUpdates)
    jungian_analysis: dict[Dimension, JungianAssessment] = Field(default_factory=dict)
    jungian_guidance: JungianGuidance | None = None
    jungian_context: JungianContext | None = None
    needs_summary: str = Field(default='', max_length=2000)
    suggested_reply: str = Field(max_length=4000)
    avoid_reply: str = Field(default='', max_length=4000)
    questions: list[str] = Field(default_factory=list, max_length=20)
    next_steps: list[str] = Field(default_factory=list, max_length=20)
    reasoning_summary: str = Field(min_length=1, max_length=4000)

    @field_validator('evidence_message_ids')
    @classmethod
    def unique_ids(cls, v):
        if len(v) != len(set(v)) or any(x < 1 for x in v):
            raise ValueError('证据 ID 必须为不重复的正整数')
        return v

class AnalyzeIn(Strict):
    evidence_message_ids: list[int] = Field(default_factory=list, max_length=100)
    external_consent: bool = False
    manual_proposal: Proposal | None = None

class ReviewIn(Strict):
    action: Literal['approve', 'reject']
    expected_version: int = Field(ge=0)
    note: str = Field(default='', max_length=2000)
    edited_proposal: Proposal | None = None

class RestoreIn(Strict):
    version: int = Field(ge=0)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)

class TextImportIn(Strict):
    customer_id: int
    text: str = Field(min_length=1, max_length=500000)

class ConfirmIn(Strict):
    rows: list[dict] = Field(min_length=1, max_length=2000)

class FeedbackIn(Strict):
    useful: bool
    note: str = Field(default='', max_length=2000)

class SettingsIn(Strict):
    company_name: str = Field(min_length=1, max_length=100)
    external_ai_enabled: bool = False
    data_policy: str = Field(default='', max_length=4000)
