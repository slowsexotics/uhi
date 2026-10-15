import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch
import test_isolation
from test_isolation import TEMP
import uhi_briefing as b
from test_beginner import result

class Response:
    def __init__(self,value): self.value=value
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,size): return json.dumps(self.value).encode()

class InferenceTests(unittest.TestCase):
    def setUp(self):
        for p in Path(TEMP.name).glob('*'):
            if p.is_file(): p.unlink()
        self.context={'creator_profile':{'niche':'Cooking'},'learning_history':[], 'recent_briefings':[]}
        self.env=patch.dict(os.environ,{'UHI_INFERENCE_APPROVED':'1','UHI_MODEL':'test:small','UHI_OLLAMA_URL':'http://127.0.0.1:11434'})
        self.env.start(); self.addCleanup(self.env.stop)

    def test_backend_payload_is_stateless_and_loaded_model_only(self):
        calls=[]
        def opened(request,timeout):
            calls.append((request,timeout))
            if request.full_url.endswith('/api/ps'): return Response({'models':[{'name':'test:small'}]})
            return Response({'done':True,'message':{'content':json.dumps(result(self.context)[0])}})
        with patch('urllib.request.OpenerDirector.open',side_effect=opened): value,model=b.local_inference(self.context)
        self.assertEqual(model,'test:small')
        self.assertEqual(len(calls),2)
        req,timeout=calls[1]; payload=json.loads(req.data)
        self.assertEqual(timeout,90)
        self.assertEqual(payload['model'],'test:small')
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['format'], b.BRIEFING_SCHEMA)
        self.assertEqual(payload['format']['type'], 'object')
        self.assertFalse(payload['format']['additionalProperties'])
        self.assertEqual(set(payload['format']['required']), set(b.BRIEFING_FIELDS))
        self.assertEqual(payload['options'], {'num_predict':1200, 'num_ctx':4096})
        self.assertNotIn('keep_alive',payload) # no unload of a shared loaded model
        self.assertNotIn('session_id',payload)
        self.assertEqual(json.loads(payload['messages'][1]['content']),self.context)
        self.assertIn('untrusted data',payload['messages'][0]['content'])
        self.assertEqual(value['recommended_action'],result(self.context)[0]['recommended_action'])

    def test_unloaded_or_missing_model_never_starts_chat(self):
        with patch('urllib.request.OpenerDirector.open',return_value=Response({'models':[]})) as opened:
            with self.assertRaisesRegex(b.BriefingError,'not already loaded'): b.local_inference(self.context)
        self.assertEqual(opened.call_count,1)
        with patch.dict(os.environ,{'UHI_MODEL':''}):
            with self.assertRaises(b.BriefingError): b.inference_configuration()

    def test_local_endpoint_validation(self):
        for value in ['http://127.0.0.1:18081','http://localhost','https://external.test','http://example.com','http://127.0.0.1:11434/other','http://user:password@127.0.0.1:11434','http://[broken','http://127.0.0.1:bad','http://127.0.0.1:11434?secret=hidden']:
            with patch.dict(os.environ,{'UHI_OLLAMA_URL':value}):
                with self.assertRaises(b.BriefingError): b.inference_configuration()
        with self.assertRaises(b.BriefingError): b.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_timeout_invalid_output_and_incomplete_inference(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=socket.timeout('PRIVATE')):
            with self.assertRaises(b.BriefingError) as error: b.local_inference(self.context)
            self.assertNotIn('PRIVATE',str(error.exception))
        for second in [{'done':False},{'done':True,'message':{'content':'{'}},{'done':True,'message':{'content':'{}'}}]:
            with patch('urllib.request.OpenerDirector.open',side_effect=[Response({'models':[{'name':'test:small'}]}),Response(second)]):
                with self.assertRaises(b.BriefingError): b.local_inference(self.context)

    def test_approved_model_must_match_saved_preference(self):
        b.save_profile({'niche':'Cooking'},{'model':'ollama/different:model'})
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(b.BriefingError,'differs'): b.local_inference(self.context)

if __name__=='__main__': unittest.main()
