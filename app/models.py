from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, Table
from sqlalchemy.orm import relationship
from .db import Base
from .core import now

user_roles = Table('user_roles', Base.metadata,
    Column('user_id', ForeignKey('users.id'), primary_key=True),
    Column('role_name', ForeignKey('roles.name'), primary_key=True))

class Timestamps:
    created_at = Column(DateTime, default=now, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)

class Department(Timestamps, Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

class Role(Base):
    __tablename__ = 'roles'
    name = Column(String(30), primary_key=True)

class User(Timestamps, Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(Text, nullable=False)
    department_id = Column(ForeignKey('departments.id'))
    scope = Column(String(20), default='own', nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)
    must_change_password = Column(Boolean, default=True, nullable=False)
    roles = relationship(Role, secondary=user_roles, lazy='selectin')

    @property
    def role(self):
        return self.roles[0].name if self.roles else 'readonly'

class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    csrf = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    key = Column(String(64), index=True, nullable=False)
    created_at = Column(DateTime, default=now, index=True, nullable=False)

class Customer(Timestamps, Base):
    __tablename__ = 'customers'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), index=True, nullable=False)
    industry = Column(String(100), default='', nullable=False)
    contact = Column(String(100), default='', nullable=False)
    contact_info = Column(String(200), default='', nullable=False)
    source = Column(String(100), default='', nullable=False)
    owner_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    department_id = Column(ForeignKey('departments.id'), index=True)
    status = Column(String(30), default='potential', nullable=False)
    last_followup_at = Column(DateTime)
    notes = Column(Text, default='', nullable=False)
    archived = Column(Boolean, default=False, nullable=False)

class Assignment(Base):
    __tablename__ = 'customer_assignments'
    user_id = Column(ForeignKey('users.id'), primary_key=True)
    customer_id = Column(ForeignKey('customers.id'), primary_key=True)

class ImportBatch(Timestamps, Base):
    __tablename__ = 'import_batches'
    id = Column(String(36), primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False)
    source = Column(String(100), nullable=False)
    rows = Column(JSON, nullable=False)
    result = Column(JSON)
    status = Column(String(20), default='preview', nullable=False)

class Message(Timestamps, Base):
    __tablename__ = 'conversation_messages'
    id = Column(Integer, primary_key=True)
    customer_id = Column(ForeignKey('customers.id'), nullable=False, index=True)
    batch_id = Column(ForeignKey('import_batches.id'))
    speaker = Column(String(20), nullable=False)
    sent_at = Column(DateTime, nullable=False, index=True)
    content = Column(Text, nullable=False)
    source = Column(String(200), default='manual', nullable=False)
    created_by = Column(ForeignKey('users.id'), nullable=False)
    fingerprint = Column(String(64), unique=True, nullable=False)

class Profile(Timestamps, Base):
    __tablename__ = 'customer_profiles'
    customer_id = Column(ForeignKey('customers.id'), primary_key=True)
    version = Column(Integer, default=0, nullable=False)
    business = Column(JSON, nullable=False)
    scores = Column(JSON, nullable=False)
    field_meta = Column(JSON, default=dict, nullable=False)

class ChangeRequest(Timestamps, Base):
    __tablename__ = 'profile_change_requests'
    id = Column(Integer, primary_key=True)
    customer_id = Column(ForeignKey('customers.id'), nullable=False, index=True)
    submitted_by = Column(ForeignKey('users.id'), nullable=False)
    base_version = Column(Integer, nullable=False)
    proposal = Column(JSON, nullable=False)
    original_proposal = Column(JSON, nullable=False)
    source = Column(String(30), nullable=False)
    status = Column(String(20), default='pending', nullable=False, index=True)
    reviewed_by = Column(ForeignKey('users.id'))
    reviewed_at = Column(DateTime)
    review_note = Column(Text, default='', nullable=False)
    applied_delta = Column(JSON)

class ProfileVersion(Base):
    __tablename__ = 'profile_versions'
    id = Column(Integer, primary_key=True)
    customer_id = Column(ForeignKey('customers.id'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    request_id = Column(ForeignKey('profile_change_requests.id'))
    actor_id = Column(ForeignKey('users.id'), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)
    __table_args__ = (UniqueConstraint('customer_id', 'version'),)

class EvidenceUse(Base):
    __tablename__ = 'evidence_uses'
    customer_id = Column(ForeignKey('customers.id'), primary_key=True)
    message_id = Column(ForeignKey('conversation_messages.id'), primary_key=True)
    request_id = Column(ForeignKey('profile_change_requests.id'), nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)

class Audit(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id'))
    action = Column(String(100), nullable=False, index=True)
    entity = Column(String(100), nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=now, index=True, nullable=False)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)

class Feedback(Base):
    __tablename__ = 'suggestion_feedback'
    request_id = Column(ForeignKey('profile_change_requests.id'), primary_key=True)
    user_id = Column(ForeignKey('users.id'), primary_key=True)
    useful = Column(Boolean, nullable=False)
    note = Column(Text, default='', nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)
