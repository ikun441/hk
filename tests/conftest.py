import os
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ['AI_MODE']='mock'
from app.main import app
from app.db import Base,get_db
from app.models import Role,User,Department
from app.auth import hasher

PASSWORD='TestOnly-Password-438!'

@pytest.fixture
def env(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "test.sqlite3"}',connect_args={'check_same_thread':False,'timeout':20})
    @event.listens_for(engine,'connect')
    def pragmas(c,r):
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory.begin() as db:
        roles={r:Role(name=r) for r in ['superadmin','admin','employee','readonly']}
        db.add_all(roles.values())
        db.add_all([Department(id=1,name='服务一部'),Department(id=2,name='服务二部')])
        db.flush()
        for uid,name,role,scope,dept in [(1,'root','superadmin','all',None),(2,'staff','employee','own',1),(3,'other','employee','own',2),(4,'reader','readonly','department',1),(5,'manager','admin','department',1),(6,'assigned','employee','assigned',2)]:
            db.add(User(id=uid,username=name,display_name=name,password_hash=hasher.hash(PASSWORD),roles=[roles[role]],scope=scope,department_id=dept,must_change_password=False))
    def override():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db]=override
    def client(name='root'):
        c=TestClient(app)
        result=c.post('/api/auth/login',json={'username':name,'password':PASSWORD},headers={'X-CRM-Request':'1'})
        assert result.status_code==200,result.text
        c.headers.update({'X-CRM-Request':'1','X-CSRF-Token':result.json()['csrf_token']})
        return c
    yield client,factory
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def root(env):
    return env[0]()

@pytest.fixture
def customer(root):
    r=root.post('/api/customers',json={'name':'星河科技','owner_id':2,'department_id':1})
    assert r.status_code==201,r.text
    return r.json()

@pytest.fixture
def message(root,customer):
    r=root.post(f'/api/customers/{customer["id"]}/messages',json={'speaker':'customer','sent_at':'2026-11-15T09:30:00+08:00','content':'请发服务费用明细，我关心响应及时性。'})
    assert r.status_code==201,r.text
    return r.json()['message']
