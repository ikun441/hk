from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import json
import os
import subprocess
import sys
from unittest.mock import patch
import pytest
from openpyxl import Workbook,load_workbook
from sqlalchemy import select
from app.models import User,Assignment,Message,Audit,Profile,ChangeRequest
from app.schemas import Proposal
from app.services.ai_service import redact,mask_value
from app.services.import_service import HEADERS
from conftest import PASSWORD


def submit(root,cid,manual=None):
    data={'manual_proposal':manual} if manual else {}
    r=root.post(f'/api/customers/{cid}/analyze',json=data)
    assert r.status_code==201,r.text
    return r.json()

def manual(cid,mid,delta=3):
    return {'customer_id':cid,'evidence_message_ids':[mid],'business_profile_updates':{'needs':['需要清晰的服务费用明细']},'jungian_updates':{'Te':delta},'suggested_reply':'我们将提供服务明细供您确认。','reasoning_summary':'客户明确询问费用明细。'}

def test_cookie_and_csrf(root):
    assert root.cookies.get('crm_session')
    r=root.post('/api/customers',json={'name':'无CSRF'},headers={'X-CSRF-Token':''})
    assert r.status_code==403
    assert root.post('/api/customers',json={'name':'跨站'},headers={'Origin':'https://attacker.example'}).status_code==403
    assert root.get('/api/auth/me').headers['cache-control']=='no-store'


def test_first_login_must_change(env):
    factory=env[1]
    with factory.begin() as db:
        db.get(User,2).must_change_password=True
    client=env[0]('staff')
    assert client.get('/api/customers').status_code==403
    assert client.post('/api/auth/password',json={'old_password':PASSWORD,'new_password':'Changed-Password-543!'}).status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'username':'staff','password':'Changed-Password-543!'}).status_code==200


def test_staff_cannot_access_other_customer(env,root,customer,message):
    client=env[0]('other')
    cid=customer['id']
    for path in [f'/customers/{cid}',f'/customers/{cid}/messages',f'/customers/{cid}/profile',f'/customers/{cid}/versions']:
        assert client.get('/api'+path).status_code==404
    assert client.post(f'/api/customers/{cid}/analyze',json={}).status_code==404
    assert client.get('/api/customers').json()['total']==0
    assert client.get('/api/dashboard').json()['total_customers']==0
    assert client.post('/api/imports/text',json={'customer_id':cid,'text':'2026-11-15 09:00 客户: 测试'}).status_code==404


def test_assigned_customer_scope(env,root,customer):
    c=deepcopy(customer)
    c={k:c[k] for k in ['name','industry','contact','contact_info','source','owner_id','department_id','status','last_followup_at','notes','authorized_user_ids']}
    c['authorized_user_ids']=[6]
    assert root.put(f'/api/customers/{customer["id"]}',json=c).status_code==200
    assigned=env[0]('assigned')
    assert assigned.get(f'/api/customers/{customer["id"]}').status_code==200
    assert assigned.get('/api/customers').json()['total']==1
    assert assigned.post('/api/customers',json={'name':'不得擅自新建'}).status_code==403


def test_readonly_backend_enforcement(env,customer):
    c=env[0]('reader')
    assert c.get(f'/api/customers/{customer["id"]}').status_code==200
    assert c.delete(f'/api/customers/{customer["id"]}').status_code==403
    assert c.post('/api/customers',json={'name':'只读写入'}).status_code==403
    assert c.get('/api/admin/users').status_code==403


def test_user_creation_and_admin_boundary(env,root):
    r=root.post('/api/admin/users',json={'username':'newstaff','display_name':'新员工','password':PASSWORD,'role':'employee','scope':'own','department_id':1})
    assert r.status_code==201,r.text
    assert r.json()['must_change_password']
    manager=env[0]('manager')
    for role,scope,dept in [('superadmin','all',None),('admin','department',1),('employee','all',1),('employee','own',2)]:
        assert manager.post('/api/admin/users',json={'username':'escalate','display_name':'越权','password':PASSWORD,'role':role,'scope':scope,'department_id':dept}).status_code==403
    assert manager.delete('/api/admin/users/1').status_code==403
    assert manager.post('/api/admin/users',json={'username':'safe','display_name':'本部员工','password':PASSWORD,'department_id':1}).status_code==201


def test_disabled_session_revoked(env,root):
    staff=env[0]('staff')
    data={'display_name':'staff','role':'employee','scope':'own','department_id':1,'active':False}
    assert root.put('/api/admin/users/2',json=data).status_code==200
    assert staff.get('/api/auth/me').status_code==401
    assert root.delete('/api/admin/users/1').status_code==409


def test_customer_search_archive_export(root,customer):
    assert root.get('/api/customers?q=星河&industry=&status=potential&owner_id=2').json()['total']==1
    assert root.get('/api/customers?q=%25').json()['total']==0
    book=load_workbook(BytesIO(root.get('/api/customers/export').content))
    assert book.active.cell(2,2).value=='星河科技'
    assert root.delete(f'/api/customers/{customer["id"]}').status_code==200
    assert root.get('/api/customers').json()['total']==0
    assert root.get('/api/customers?archived=true').json()['total']==1
    assert root.post(f'/api/customers/{customer["id"]}/analyze',json={}).status_code==409


def test_message_timezone_and_duplicates(root,customer,message):
    cid=customer['id']
    assert message['sent_at']=='2026-11-15T01:30:00Z'
    payload={'speaker':'customer','sent_at':'2026-11-15T01:30:00Z','content':message['content']}
    assert root.post(f'/api/customers/{cid}/messages',json=payload).json()['duplicate']
    payload['sent_at']='2026-11-15T09:30:00'
    assert root.post(f'/api/customers/{cid}/messages',json=payload).status_code==422


def test_text_preview_edit_partial_and_idempotent(root,customer):
    data=root.post('/api/imports/text',json={'customer_id':customer['id'],'text':'2026-11-15 10:00 客户: 第一条\n无法识别的行\n2026-11-15 10:01 员工: 回复'}).json()
    assert len(data['rows'])==3
    assert data['rows'][1]['error']
    result=root.post(f'/api/imports/{data["id"]}/confirm',json={'rows':data['rows']})
    assert result.status_code==200,result.text
    assert result.json()['inserted']==2 and result.json()['failed']==1
    result2=root.post(f'/api/imports/{data["id"]}/confirm',json={'rows':data['rows']})
    assert result2.json()==result.json()
    history=root.get(f'/api/customers/{customer["id"]}/messages').json()
    assert history['total']==2
    assert '第'.encode() not in root.get(f'/api/imports/{data["id"]}/errors').content[:3]
    fixed=root.post('/api/imports/text',json={'customer_id':customer['id'],'text':'待修正'}).json()
    fixed['rows'][0].update(sent_at='2026-11-15 10:05',speaker='customer',content='人工修正')
    result=root.post(f'/api/imports/{fixed["id"]}/confirm',json={'rows':fixed['rows']}).json()
    assert result['inserted']==1


def xlsx(rows):
    book=Workbook();sheet=book.active;sheet.append(HEADERS)
    for r in rows:sheet.append(r)
    out=BytesIO();book.save(out);return out.getvalue()


def test_multi_customer_excel_invalid_rows_and_duplicate(root,customer):
    second=root.post('/api/customers',json={'name':'第二家企业'}).json()
    content=xlsx([[customer['id'],'2026-11-15 10:00','客户','价格明细','excel'],[second['name'],'2026-11-15 10:01','员工','收到','excel'],[customer['id'],'错误时间','客户','有错','excel'],[9999,'2026-11-15 10:00','客户','未知客户','excel'],[customer['id'],'2026-11-15 10:02','客户','=1+1','excel']])
    r=root.post('/api/imports/excel',files={'file':('chat.xlsx',content)})
    assert r.status_code==200,r.text
    batch=r.json()
    assert [x['row'] for x in batch['rows'] if x.get('error')]==[4,5,6]
    # Formula text remains a literal on confirmation; require user to repair or omit flagged row.
    result=root.post(f'/api/imports/{batch["id"]}/confirm',json={'rows':batch['rows']}).json()
    assert result['inserted']==2 and result['failed']==3
    batch2=root.post('/api/imports/excel',files={'file':('chat.xlsx',content)}).json()
    result=root.post(f'/api/imports/{batch2["id"]}/confirm',json={'rows':batch2['rows']}).json()
    assert result['duplicates']==2


def test_import_rechecks_permission_and_batch_owner(env,root,customer):
    staff=env[0]('staff')
    batch=staff.post('/api/imports/text',json={'customer_id':customer['id'],'text':'2026-11-15 10:00 客户: 数据'}).json()
    assert root.get('/api/imports/'+batch['id']).status_code==404
    with env[1].begin() as db:
        from app.models import Customer
        db.get(Customer,customer['id']).owner_id=3
    result=staff.post('/api/imports/'+batch['id']+'/confirm',json={'rows':batch['rows']})
    assert result.json()['failed']==1


def test_mock_proposal_does_not_mutate_before_approval(root,customer,message):
    cid=customer['id'];req=submit(root,cid)
    assert req['source']=='mock' and req['status']=='pending'
    before=root.get(f'/api/customers/{cid}/profile').json()
    assert before['version']==0 and before['business']['concerns']==[]
    approved=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0})
    assert approved.status_code==200,approved.text
    after=root.get(f'/api/customers/{cid}/profile').json()
    assert after['version']==1 and after['business']['concerns']
    assert after['field_meta']['concerns']['evidence_message_ids']==[message['id']]
    assert set(after['scores'].values())=={50}


def test_duplicate_evidence_no_extra_score_and_restore(root,customer,message):
    cid=customer['id'];proposal=manual(cid,message['id'],7)
    for version in [0,1]:
        req=submit(root,cid,proposal)
        r=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':version})
        assert r.status_code==200,r.text
    profile=root.get(f'/api/customers/{cid}/profile').json()
    assert profile['scores']['Te']==57
    assert root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':2}).status_code==409
    assert root.post(f'/api/customers/{cid}/restore',json={'version':0,'expected_version':2,'reason':'错误提案回滚'}).status_code==200
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==50
    assert root.get(f'/api/customers/{cid}/versions').json()['items'][0]['snapshot']['score_delta']['Te']==-7
    req=submit(root,cid,proposal)
    assert root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':3}).status_code==200
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==50
    assert root.get(f'/api/customers/{cid}/versions').json()['total']==5


def test_modify_approve_and_reject(root,customer,message):
    cid=customer['id'];req=submit(root,cid)
    edited=deepcopy(req['proposal']);edited['business_profile_updates']={'needs':['经人工核实的需求']};edited['jungian_updates']['Te']=2
    edited['jungian_analysis']['Te']={'confidence':'low','reasoning':'人工复核费用明细的结构化表达线索','expression_tip':'逐项说明费用明细','evidence':[{'message_id':message['id'],'quote':message['content']}]}
    r=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0,'edited_proposal':edited,'note':'核对原文'})
    assert r.status_code==200,r.text
    assert root.get(f'/api/customers/{cid}/profile').json()['business']['needs']==['经人工核实的需求']
    req=submit(root,cid)
    assert root.post(f'/api/requests/{req["id"]}/review',json={'action':'reject','expected_version':1,'note':'证据不足'}).status_code==200
    assert root.get(f'/api/customers/{cid}/profile').json()['version']==1


def test_parallel_review_conflict_atomic(root,customer,message,env):
    cid=customer['id'];a=submit(root,cid);b=submit(root,cid);client2=env[0]()
    def review(args):
        c,r=args
        return c.post(f'/api/requests/{r["id"]}/review',json={'action':'approve','expected_version':0}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(review,[(root,a),(client2,b)]))
    assert sorted(codes)==[200,409]
    assert root.get(f'/api/customers/{cid}/profile').json()['version']==1
    changes=root.get('/api/requests?status=all').json()['items']
    assert sorted(x['status'] for x in changes)==['approved','pending']


def test_wrong_customer_evidence_and_bad_ai_schema(root,customer,message):
    c=root.post('/api/customers',json={'name':'别家客户'}).json()
    wrong=manual(c['id'],message['id'])
    assert root.post(f'/api/customers/{c["id"]}/analyze',json={'manual_proposal':wrong}).status_code==422
    wrong=manual(customer['id'],message['id'],100)
    assert root.post(f'/api/customers/{customer["id"]}/analyze',json={'manual_proposal':wrong}).status_code==422
    wrong=manual(customer['id'],message['id']);wrong['sql']='DROP TABLE users'
    assert root.post(f'/api/customers/{customer["id"]}/analyze',json={'manual_proposal':wrong}).status_code==422


def test_real_ai_gate_and_malformed_output(root,customer,message,monkeypatch):
    monkeypatch.setenv('AI_MODE','real');monkeypatch.setenv('AI_API_KEY','test-only-key')
    assert root.post(f'/api/customers/{customer["id"]}/analyze',json={'external_consent':True}).status_code==409
    assert root.put('/api/admin/settings',json={'company_name':'企客','external_ai_enabled':True,'data_policy':'仅授权、脱敏业务聊天'}).status_code==200
    response=type('Response',(),{'raise_for_status':lambda self:None,'json':lambda self:{'choices':[{'message':{'content':'not-json'}}]}})()
    with patch('app.services.ai_service.httpx.Client') as ai_client:
        ai_client.return_value.__enter__.return_value.post.return_value=response
        r=root.post(f'/api/customers/{customer["id"]}/analyze',json={'external_consent':True})
    assert r.status_code==502
    assert 'test-only-key' not in r.text
    assert root.get(f'/api/customers/{customer["id"]}/profile').json()['version']==0


def test_refusal_boundaries(root,customer):
    cid=customer['id']
    root.post(f'/api/customers/{cid}/messages',json={'speaker':'customer','sent_at':'2026-11-15T11:00:00+08:00','content':'请不要再联系我，不要推销。'})
    req=submit(root,cid)
    assert '停止营销' in req['proposal']['suggested_reply']
    assert '停止营销' in ''.join(req['proposal']['next_steps'])


def test_redaction():
    assert '13812345678' not in redact('手机13812345678，邮箱test@example.com，证件123456789012345678')
    value=mask_value({'messages':['联系人张三，公司星河科技，13812345678']},['张三','星河科技'])
    assert '张三' not in json.dumps(value,ensure_ascii=False)


def test_audit_trace(root,customer,message,env):
    req=submit(root,customer['id'])
    root.post(f'/api/requests/{req["id"]}/feedback',json={'useful':True,'note':'有参考价值'})
    root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0})
    actions={a['action'] for a in root.get('/api/admin/audits?page_size=100').json()['items']}
    assert {'auth.login','customer.create','message.add','profile.submit','profile.approve','suggestion.feedback'}.issubset(actions)


def test_cli_initialize_backup_restore(tmp_path):
    path=Path(__file__).resolve().parent.parent
    database=tmp_path/'cli.sqlite3';backup=tmp_path/'backup.sqlite3'
    environ={**os.environ,'DATABASE_URL':f'sqlite:///{database}','ADMIN_PASSWORD':PASSWORD}
    def run(*args):
        return subprocess.run([sys.executable,'scripts/manage.py',*args],cwd=path,env=environ,capture_output=True,text=True)
    assert run('init-admin').returncode==0
    assert run('init-admin').returncode!=0
    assert run('backup',str(backup)).returncode==0
    import sqlite3
    with sqlite3.connect(database) as db:db.execute("UPDATE users SET display_name='changed'")
    assert run('restore',str(backup)).returncode!=0
    assert run('restore',str(backup),'--confirm-stopped').returncode==0
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT display_name FROM users').fetchone()[0]=='系统管理员'
        assert db.execute("SELECT count(*) FROM audit_logs WHERE action='database.restore'").fetchone()[0]==1


def test_invalid_excel_headers_and_payloads(root):
    assert root.post('/api/imports/excel',files={'file':('bad.xlsx',b'not a workbook')}).status_code==422
    assert root.post('/api/imports/excel',files={'file':('bad.csv',b'anything')}).status_code==422
    book=Workbook();book.active.append(['错误表头']);out=BytesIO();book.save(out)
    assert root.post('/api/imports/excel',files={'file':('bad.xlsx',out.getvalue())}).status_code==422


def test_same_request_parallel_review(root,customer,message,env):
    req=submit(root,customer['id']);second=env[0]()
    def approve(c):
        return c.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(approve,[root,second]))
    assert sorted(codes)==[200,409]
    assert root.get(f'/api/customers/{customer["id"]}/versions').json()['total']==2


def test_score_bounds_and_used_evidence_ledger(root,customer,env):
    cid=customer['id']
    with env[1].begin() as db:
        profile=db.get(Profile,cid)
        profile.scores={k:99 for k in profile.scores}
    msg=root.post(f'/api/customers/{cid}/messages',json={'speaker':'customer','sent_at':'2026-11-15T09:00:00+08:00','content':'核实一条新证据'}).json()['message']
    req=submit(root,cid,manual(cid,msg['id'],10))
    result=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0})
    assert result.status_code==200,result.text
    assert result.json()['applied_delta']['Te']==1
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==100
    assert root.get(f'/api/customers/{cid}/versions').json()['items'][0]['snapshot']['score_delta']['Te']==1


def test_approved_edit_retains_original(root,customer,message):
    req=submit(root,customer['id']);edited=deepcopy(req['proposal']);edited['suggested_reply']='经人工修订的话术'
    r=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0,'edited_proposal':edited})
    assert r.status_code==200,r.text
    assert r.json()['proposal']['suggested_reply']=='经人工修订的话术'
    assert r.json()['original_proposal']['suggested_reply']==req['proposal']['suggested_reply']


def test_employee_cannot_approve_or_restore(env,root,customer,message):
    req=submit(root,customer['id']);staff=env[0]('staff')
    assert staff.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0}).status_code==403
    assert staff.post(f'/api/customers/{customer["id"]}/restore',json={'version':0,'expected_version':0,'reason':'擅自恢复'}).status_code==403


def test_password_whitespace_preserved(root,env):
    new=' Spaces-Matter-Here! '
    assert root.post('/api/auth/password',json={'old_password':PASSWORD,'new_password':new}).status_code==200
    r=root.post('/api/auth/login',json={'username':'root','password':new})
    assert r.status_code==200,r.text
    assert root.post('/api/auth/login',json={'username':'root','password':new.strip()}).status_code==401


def test_real_ai_valid_response_and_redacted_payload(root,customer,message,monkeypatch):
    monkeypatch.setenv('AI_MODE','real');monkeypatch.setenv('AI_API_KEY','never-expose-this-key')
    root.put('/api/admin/settings',json={'company_name':'企客','external_ai_enabled':True,'data_policy':'已授权业务数据的脱敏处理'})
    proposal=manual(customer['id'],message['id'])
    from app.schemas import Proposal
    proposal=Proposal.model_validate(proposal).model_dump()
    proposal['jungian_analysis']={d:{'confidence':'insufficient','reasoning':'缺乏此维度线索','evidence':[],'expression_tip':''} for d in proposal['jungian_updates']}
    proposal['jungian_analysis']['Te']={'confidence':'low','reasoning':'客户明确要求费用明细','expression_tip':'提供逐项费用清单','evidence':[{'message_id':message['id'],'quote':message['content']}]}
    proposal['jungian_guidance']={'summary':'Te线索使本次话术采用费用清单结构','dimensions':['Te'],'wording_tips':['逐项说明费用范围'],'basis':'proposal_preview'}
    response=type('Response',(),{'raise_for_status':lambda self:None,'json':lambda self:{'choices':[{'message':{'content':json.dumps(proposal)}}]}})()
    with patch('app.services.ai_service.httpx.Client') as client:
        external=client.return_value.__enter__.return_value
        external.post.return_value=response
        result=root.post(f'/api/customers/{customer["id"]}/analyze',json={'external_consent':True})
        assert result.status_code==201,result.text
        payload=external.post.call_args.kwargs['json']
        assert 'approved_jungian' in payload['messages'][1]['content']
        assert 'scoring_message_ids' in payload['messages'][1]['content']
        assert '话术必须落实' in payload['messages'][0]['content'] or '推荐话术必须落实' in payload['messages'][0]['content']
        assert 'never-expose-this-key' not in result.text
    assert root.get(f'/api/customers/{customer["id"]}/profile').json()['version']==0


def test_offline_api_documentation(root):
    docs=root.get('/docs')
    assert docs.status_code==200
    assert '/api/customers' in docs.text
    assert 'cdn' not in docs.text.lower()
    schema=root.get('/openapi.json')
    assert schema.status_code==200 and '/api/customers/{customer_id}/analyze' in schema.json()['paths']


def test_ambiguous_excel_time_and_fractional_customer_id(root,customer):
    content=xlsx([[float(customer['id'])+.5,'2026-11-15 09:00','客户','错误ID','excel'],[customer['id'],'2026-11-15','客户','缺少时间','excel']])
    r=root.post('/api/imports/excel',files={'file':('chat.xlsx',content)})
    assert r.status_code==200,r.text
    assert all(row.get('error') for row in r.json()['rows'])


def test_validation_never_echoes_password(root):
    r=root.post('/api/admin/users',json={'username':'bad','display_name':'测试','password':'secretshort'})
    assert r.status_code==422
    assert 'secretshort' not in r.text


def test_employee_reads_processing_rules_without_secrets(root,env):
    root.put('/api/admin/settings',json={'company_name':'团队甲','external_ai_enabled':True,'data_policy':'仅处理已授权及脱敏的服务聊天'})
    response=env[0]('staff').get('/api/workspace')
    assert response.status_code==200
    assert response.json()['company_name']=='团队甲'
    assert response.json()['data_policy']=='仅处理已授权及脱敏的服务聊天'
    assert 'api_key' not in response.text.lower()


def test_archived_customer_pending_request_can_be_rejected(root,customer,message):
    req=submit(root,customer['id'])
    root.delete(f'/api/customers/{customer["id"]}')
    assert root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':0}).status_code==409
    assert root.post(f'/api/requests/{req["id"]}/review',json={'action':'reject','expected_version':0,'note':'客户已归档'}).status_code==200
