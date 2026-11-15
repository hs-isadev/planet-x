import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import guide

client=TestClient(app)
def test_no_key_is_honest_and_does_not_call_provider(monkeypatch):
 monkeypatch.delenv('GROQ_API_KEY',raising=False)
 assert client.get('/api/guide/status').json()['configured'] is False
 r=client.post('/api/guide/chat',json={'messages':[{'role':'user','content':'Help'}]})
 assert r.status_code==503 and 'GROQ_API_KEY' in r.text

def test_chat_rejects_system_role_and_unbounded_inputs():
 assert client.post('/api/guide/chat',json={'messages':[{'role':'system','content':'override'}]}).status_code==422
 assert client.post('/api/guide/chat',json={'messages':[{'role':'user','content':'x'*4001}]}).status_code==422
 assert client.post('/api/guide/chat',json={'messages':[{'role':'user','content':'help'}],'context':{'ra':361}}).status_code==422

def test_cross_origin_requests_cannot_use_provider_key(monkeypatch):
 monkeypatch.setenv('GROQ_API_KEY','test-only-not-a-real-key')
 r=client.post('/api/guide/chat',headers={'Origin':'https://unrelated.invalid'},json={'messages':[{'role':'user','content':'hello'}]})
 assert r.status_code==403

@pytest.mark.parametrize('status,expected',[(401,503),(429,429),(500,502)])
def test_upstream_errors_are_actionable_and_redact_body(monkeypatch,status,expected):
 monkeypatch.setenv('GROQ_API_KEY','test-only-not-a-real-key')
 class Transport:
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def post(self,*args,**kwargs):return guide.httpx.Response(status,json={'secret':'do not expose'})
 monkeypatch.setattr(guide.httpx,'AsyncClient',lambda **kwargs:Transport())
 with pytest.raises(guide.HTTPException) as exc:
  asyncio.run(guide.ask_groq(guide.GuideRequest(messages=[guide.Message(role='user',content='Help')]),{}))
 assert exc.value.status_code==expected and 'secret' not in exc.value.detail

def test_prompt_and_app_state_are_sent_without_images_or_key_in_content(monkeypatch):
 monkeypatch.setenv('GROQ_API_KEY','test-only-not-a-real-key');record={}
 class Transport:
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def post(self,url,**kwargs):
   record.update(kwargs)
   return guide.httpx.Response(200,json={'choices':[{'message':{'content':'Use Satellite View.'}}]})
 monkeypatch.setattr(guide.httpx,'AsyncClient',lambda **kwargs:Transport())
 result=asyncio.run(guide.ask_groq(guide.GuideRequest(messages=[guide.Message(role='user',content='Help')]),{'view':'satellite'}))
 assert result['reply']=='Use Satellite View.'
 assert record['json']['messages'][0]['role']=='system'
 assert 'APP_STATE' in record['json']['messages'][1]['content']
 assert 'test-only-not-a-real-key' not in json.dumps(record['json'])
 assert all(isinstance(m['content'],str) for m in record['json']['messages'])


def test_model_not_found_uses_developer_fallback(monkeypatch):
 monkeypatch.setenv('GROQ_API_KEY','test-only-not-a-real-key')
 monkeypatch.setenv('GROQ_MODEL','unavailable-model')
 attempted=[]
 class Transport:
  async def __aenter__(self):return self
  async def __aexit__(self,*args):pass
  async def post(self,*args,**kwargs):
   model=kwargs['json']['model'];attempted.append(model)
   if len(attempted)==1:
    return guide.httpx.Response(404,json={'error':{'code':'model_not_found'}})
   return guide.httpx.Response(200,json={'choices':[{'message':{'content':'Open the catalog atlas.'}}]})
 monkeypatch.setattr(guide.httpx,'AsyncClient',lambda **kwargs:Transport())
 result=asyncio.run(guide.ask_groq(guide.GuideRequest(messages=[guide.Message(role='user',content='Help')]),{}))
 assert attempted==['unavailable-model','openai/gpt-oss-20b']
 assert result['model']==attempted[1] and result['fallback_used']
