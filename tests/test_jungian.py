from copy import deepcopy
from sqlalchemy import select
from app.models import EvidenceUse
from app.schemas import Proposal

DIMS=('Ne','Ni','Se','Si','Te','Ti','Fe','Fi')

def add(root,cid,content,speaker='customer',minute=0):
    r=root.post(f'/api/customers/{cid}/messages',json={'speaker':speaker,'sent_at':f'2026-11-15T12:{minute:02d}:00+08:00','content':content})
    assert r.status_code==201,r.text
    return r.json()['message']

def analyze(root,cid,ids=None,manual=None):
    body={'evidence_message_ids':ids or []}
    if manual:body={'manual_proposal':manual}
    r=root.post(f'/api/customers/{cid}/analyze',json=body)
    assert r.status_code==201,r.text
    return r.json()

def approve(root,req):
    r=root.post(f'/api/requests/{req["id"]}/review',json={'action':'approve','expected_version':req['base_version']})
    assert r.status_code==200,r.text
    return r.json()

def proposal(cid,msg,dim='Te',delta=2):
    p=Proposal(customer_id=cid,evidence_message_ids=[msg['id']],jungian_updates={dim:delta},suggested_reply='提供表格和清单。',reasoning_summary='基于客户的原文表达线索。').model_dump()
    p['jungian_analysis']={d:{'confidence':'insufficient','evidence':[],'reasoning':'没有此维度线索','expression_tip':''} for d in DIMS}
    p['jungian_analysis'][dim]={'confidence':'low','evidence':[{'message_id':msg['id'],'quote':msg['content']}],'reasoning':'明确提出结构化表达要求','expression_tip':'先给对照表，再列行动清单'}
    p['jungian_guidance']={'summary':f'{dim}参与表达组织：先给结构化对照和清单。','dimensions':[dim],'wording_tips':['用清单说明服务范围'],'basis':'proposal_preview'}
    return p

def test_mock_evidence_moves_score_only_after_approval(root,customer):
    cid=customer['id'];m=add(root,cid,'请用表格逐项列出清单，方便我们对照。')
    req=analyze(root,cid)
    p=req['proposal'];assert p['jungian_updates']['Te']==2
    assert p['jungian_context']['current_scores']['Te']==50
    assert p['jungian_context']['projected_scores']['Te']==52
    assert 'Te' in p['jungian_guidance']['dimensions']
    assert p['jungian_analysis']['Te']['evidence'][0]['message_id']==m['id']
    assert '结构化' in p['suggested_reply']
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==50
    approve(root,req)
    final=root.get(f'/api/customers/{cid}/profile').json()
    assert final['scores']['Te']==52
    assert final['field_meta']['jungian']['guidance']['basis']=='approved_profile'
    assert final['field_meta']['jungian']['last_delta']['Te']==2


def test_no_evidence_does_not_force_nonzero(root,customer):
    cid=customer['id'];add(root,cid,'你好，谢谢。')
    p=analyze(root,cid)['proposal']
    assert set(p['jungian_analysis'])==set(DIMS)
    assert all(v==0 for v in p['jungian_updates'].values())
    assert p['jungian_guidance']['basis']=='insufficient'
    assert p['jungian_guidance']['dimensions']==[]


def test_employee_statements_not_scoring_evidence(root,customer):
    cid=customer['id'];m=add(root,cid,'请用表格清单说明','employee')
    p=analyze(root,cid)['proposal'];assert all(v==0 for v in p['jungian_updates'].values())
    bad=proposal(cid,m)
    assert root.post(f'/api/customers/{cid}/analyze',json={'manual_proposal':bad}).status_code==422


def test_fabricated_quote_and_no_reason_rejected(root,customer):
    cid=customer['id'];m=add(root,cid,'请用表格说明。');bad=proposal(cid,m)
    bad['jungian_analysis']['Te']['evidence'][0]['quote']='客户根本没有说过的内容'
    assert root.post(f'/api/customers/{cid}/analyze',json={'manual_proposal':bad}).status_code==422
    bad=proposal(cid,m);bad['jungian_analysis']['Te']['reasoning']=''
    assert root.post(f'/api/customers/{cid}/analyze',json={'manual_proposal':bad}).status_code==422


def test_mixed_old_and_new_evidence_scores_new_only(root,customer,env):
    cid=customer['id'];old=add(root,cid,'请用表格列清单。')
    first=analyze(root,cid,manual=proposal(cid,old));approve(root,first)
    new=add(root,cid,'还请逐项列出责任清单。',minute=2)
    p=proposal(cid,new,delta=3)
    p['evidence_message_ids']=[old['id'],new['id']]
    # Old conversation context does not invalidate a fresh per-dimension quote.
    second=analyze(root,cid,manual=p)
    assert second['proposal']['jungian_context']['effective_deltas']['Te']==3
    result=approve(root,second)
    assert result['applied_delta']['Te']==3
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==55
    third=analyze(root,cid,manual=p)
    assert third['proposal']['jungian_context']['effective_deltas']['Te']==0
    assert new['id'] in third['proposal']['jungian_context']['excluded_evidence_message_ids']
    result=approve(root,third);assert all(v==0 for v in result['applied_delta'].values())
    with env[1]() as db:
        assert len(list(db.scalars(select(EvidenceUse).where(EvidenceUse.customer_id==cid))))==2


def test_evidence_counted_only_when_used_for_scoring(root,customer,env):
    cid=customer['id'];a=add(root,cid,'请用表格列清单。');b=add(root,cid,'你好，谢谢。',minute=2)
    p=proposal(cid,a);p['evidence_message_ids']=[a['id'],b['id']]
    approve(root,analyze(root,cid,manual=p))
    with env[1]() as db:
        ids=list(db.scalars(select(EvidenceUse.message_id).where(EvidenceUse.customer_id==cid)))
    assert ids==[a['id']]


def test_refusal_overrides_jungian_style_suggestions(root,customer):
    cid=customer['id'];add(root,cid,'请用表格说明，另外不要再联系我，不要推销。')
    p=analyze(root,cid)['proposal']
    assert '停止营销' in p['suggested_reply']
    assert '拒绝' in p['jungian_guidance']['summary']
    assert all('停止' in tip for tip in p['jungian_guidance']['wording_tips'])


def test_restore_keeps_evidence_ledger_and_explains_no_rescore(root,customer):
    cid=customer['id'];m=add(root,cid,'请用表格列清单。')
    p=proposal(cid,m);approve(root,analyze(root,cid,manual=p))
    r=root.post(f'/api/customers/{cid}/restore',json={'version':0,'expected_version':1,'reason':'验证回退'})
    assert r.status_code==200
    req=analyze(root,cid,manual=p)
    assert req['proposal']['jungian_context']['effective_deltas']['Te']==0
    assert req['proposal']['jungian_guidance']['basis']=='evidence_only'
    approve(root,req)
    assert root.get(f'/api/customers/{cid}/profile').json()['scores']['Te']==50


def test_real_json_request_and_truncation_rejected(root,customer,monkeypatch):
    import json
    from unittest.mock import patch
    monkeypatch.setenv('AI_MODE','real');monkeypatch.setenv('AI_API_KEY','test-key-not-secret')
    monkeypatch.setenv('AI_BASE_URL','https://api.deepseek.com')
    root.put('/api/admin/settings',json={'company_name':'测试','external_ai_enabled':True,'data_policy':'仅合成数据'})
    cid=customer['id'];m=add(root,cid,'请用表格清单说明。');p=proposal(cid,m)
    response=type('Response',(),{'raise_for_status':lambda self:None,'json':lambda self:{'choices':[{'finish_reason':'length','message':{'content':json.dumps(p)}}]}})()
    with patch('app.services.ai_service.httpx.Client') as client:
        external=client.return_value.__enter__.return_value;external.post.return_value=response
        r=root.post(f'/api/customers/{cid}/analyze',json={'external_consent':True})
        assert r.status_code==502
        body=external.post.call_args.kwargs['json']
        assert body['thinking']=={'type':'disabled'}
        assert body['max_tokens']>=8000
    assert root.get(f'/api/customers/{cid}/profile').json()['version']==0


def test_real_positive_delta_requires_actual_guidance_mapping(root,customer,monkeypatch):
    import json
    from unittest.mock import patch
    monkeypatch.setenv('AI_MODE','real');monkeypatch.setenv('AI_API_KEY','test-key-not-secret')
    root.put('/api/admin/settings',json={'company_name':'测试','external_ai_enabled':True,'data_policy':'仅合成数据'})
    cid=customer['id'];m=add(root,cid,'请用表格清单说明。');p=proposal(cid,m)
    p['jungian_guidance']['dimensions']=[]
    response=type('Response',(),{'raise_for_status':lambda self:None,'json':lambda self:{'choices':[{'message':{'content':json.dumps(p)}}]}})()
    with patch('app.services.ai_service.httpx.Client') as client:
        client.return_value.__enter__.return_value.post.return_value=response
        r=root.post(f'/api/customers/{cid}/analyze',json={'external_consent':True})
        assert r.status_code==502
