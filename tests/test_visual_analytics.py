from datetime import datetime
from app.api import customers as customer_api


def test_dashboard_charts_match_authorized_records(env,root,customer,message):
    employee=env[0]('staff');outsider=env[0]('other')
    visible=employee.get('/api/dashboard').json()
    assert sum(visible['charts']['customer_status'].values())==visible['total_customers']==1
    assert visible['charts']['message_total']==1
    assert sum(r['messages'] for r in visible['charts']['activity'])==1
    assert len(visible['charts']['activity'])==14
    hidden=outsider.get('/api/dashboard').json()
    assert hidden['charts']['message_total']==0
    assert sum(hidden['charts']['customer_status'].values())==0
    assert sum(r['messages'] for r in hidden['charts']['activity'])==0
    assert sum(hidden['charts']['approval_status'].values())==0


def test_insights_return_real_versions_and_counts(root,customer,message):
    cid=customer['id']
    r=root.get(f'/api/customers/{cid}/insights')
    assert r.status_code==200,r.text
    data=r.json()
    assert data['message_count']==1
    assert data['message_speakers']=={'customer':1,'employee':0}
    assert data['version_total']==1 and data['versions'][0]['version']==0
    assert all(x==50 for x in data['versions'][0]['scores'].values())
    req=root.post(f'/api/customers/{cid}/analyze',json={}).json()
    assert root.get(f'/api/customers/{cid}/insights').json()['request_status']['pending']==1
    approved=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0})
    assert approved.status_code==200,approved.text
    data=root.get(f'/api/customers/{cid}/insights').json()
    assert [v['version'] for v in data['versions']]==[0,1]
    assert data['request_status']['approved']==1 and data['request_status']['pending']==0


def test_insight_endpoint_does_not_leak_cross_customer_history(env,customer,message):
    outsider=env[0]('other')
    assert outsider.get(f'/api/customers/{customer["id"]}/insights').status_code==404


def test_activity_dates_use_shanghai_calendar(root,customer,monkeypatch):
    monkeypatch.setattr(customer_api,'now',lambda:datetime(2026,11,15,16,30))
    cid=customer['id']
    r=root.post(f'/api/customers/{cid}/messages',json={'speaker':'customer','sent_at':'2026-11-16T00:05:00+08:00','content':'跨北京时间零点的消息'})
    assert r.status_code==201,r.text
    rows=root.get('/api/dashboard').json()['charts']['activity']
    assert rows[-1]['date']=='2026-11-16' and rows[-1]['messages']==1


def test_company_search_respects_scope_and_handles_literal_keywords(env,root,customer):
    cid=customer['id']
    assert root.get('/api/customers',params={'q':'星河'}).json()['total']==1
    assert root.get('/api/customers',params={'q':'不存在的公司'}).json()['total']==0
    assert root.get('/api/customers',params={'q':'%'}).json()['total']==0
    assert env[0]('other').get('/api/customers',params={'q':'星河'}).json()['total']==0
    assert root.get('/api/customers',params={'q':'星河','status':'following'}).json()['total']==0
