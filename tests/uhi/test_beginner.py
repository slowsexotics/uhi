import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_isolation
from test_isolation import server, uhi_state, TEMP, DASHBOARD
import uhi_briefing as briefing
from http_fixture import request


def result(context):
    previous=context['learning_history']
    learned=previous[0]['response'] if previous else ''
    task='Record a hands-only recipe demonstration' if 'camera' in learned else 'Film one step of a favorite recipe'
    return {'personal_context':'Saved cooking goal. '+learned, 'recommended_action':task,
            'why':'It fits your cooking interest and saved feedback.',
            'steps':['Choose one recipe step.','Record a short demonstration on your phone.'],
            'done_when':'One short clip is saved; posting is optional.',
            'question':'How much time do you have to record?'}, 'test-only-mock-inference'


class BeginnerTests(unittest.TestCase):
    def setUp(self):
        for p in Path(TEMP.name).glob('*'):
            if p.is_file(): p.unlink()

    def onboard(self, **extra):
        code,_,body=request('/api/onboarding/save','POST',data=dict(name='Alex',niche='Cooking',goal='Make my first recipe clip',**extra))
        self.assertEqual(code,200,body)
        return json.loads(body)

    def generate(self,key='first-request-0001'):
        code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':key})
        self.assertEqual(code,200,body)
        return json.loads(body)['briefing']

    def test_full_beginner_learning_loop_and_restart(self):
        self.onboard()
        self.assertEqual(server.get_latest_snapshots(),{})
        self.assertFalse(any(x['connected'] for x in server.get_accounts_status().values()))
        contexts=[]
        def infer(context): contexts.append(context); return result(context)
        with patch.object(briefing,'local_inference',side_effect=infer):
            first=self.generate()
            self.assertEqual(first['completion_status'],'in_progress')
            self.assertEqual(first['delivery_status'],'not_requested')
            self.assertEqual(first['input_context']['creator_profile']['identity'],'Alex')
            code,_,body=request('/api/creator/briefings')
            self.assertEqual(json.loads(body)['briefings'][0]['id'],first['id'])
            code,_,body=request('/api/creator/briefings/feedback','POST',data={'briefing_id':first['id'],
                 'event_id':'feedback-event-0001','response':'I do not want my face on camera.',
                 'feedback':'I have ten minutes.','completion_status':'skipped'})
            self.assertEqual(code,200,body)
            # Fresh Python process, same temporary data directory, no background server.
            code="import uhi_briefing as b,json; print(json.dumps({'profile':b.read_profile(),'latest':b.latest()}))"
            child=subprocess.run([sys.executable,'-B','-c',code],env=dict(os.environ,PYTHONPATH=str(DASHBOARD)),capture_output=True,text=True,check=True)
            restored=json.loads(child.stdout)
            self.assertEqual(restored['latest']['user_response'],'I do not want my face on camera.')
            self.assertEqual(restored['latest']['completion_status'],'skipped')
            self.assertEqual(restored['profile']['identity'],'Alex')
            second=self.generate('second-request-0002')
        self.assertIn('camera',contexts[1]['learning_history'][0]['response'])
        self.assertIn('ten minutes',contexts[1]['learning_history'][0]['feedback'])
        self.assertNotEqual(first['recommended_action'],second['recommended_action'])
        self.assertIn('camera',second['content']['personal_context'])
        self.assertEqual(second['completion_status'],'in_progress')

    def test_duplicate_generation_and_feedback_are_idempotent(self):
        self.onboard()
        with patch.object(briefing,'local_inference',side_effect=result) as infer:
            first=self.generate(); duplicate=self.generate()
            self.assertEqual(first['id'],duplicate['id']); self.assertEqual(infer.call_count,1)
        a=briefing.save_feedback(first['id'],'feedback-event-0001','answer','','completed')
        b=briefing.save_feedback(first['id'],'feedback-event-0001','answer','','completed')
        self.assertEqual(a['completion_status'],b['completion_status'])
        with briefing.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM uhi_creator_feedback').fetchone()[0],1)
        with self.assertRaises(ValueError): briefing.save_feedback(first['id'],'feedback-event-0001','changed','','skipped')

    def test_missing_optional_profile_and_required_interest(self):
        self.onboard()
        profile=briefing.read_profile()
        self.assertEqual(profile['available_time'],'')
        self.assertEqual(profile['experience'],'')
        self.assertEqual(profile['resources'],'')
        with patch.object(briefing,'local_inference',side_effect=result): self.generate()
        briefing.save_profile({'niche':'','activities':''})
        with self.assertRaises(briefing.BriefingError): briefing.generate('missing-interest-001')

    def test_no_inference_without_approval(self):
        self.onboard()
        with patch.dict(os.environ,{'UHI_INFERENCE_APPROVED':''}), patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':'no-inference-0001'})
        self.assertEqual(code,409)
        self.assertIn('not been approved',json.loads(body)['message'])
        self.assertEqual(briefing.latest()['generation_status'],'failed')
        self.assertIsNone(briefing.latest()['content'])

    def test_failed_inference_and_retry_keep_one_record(self):
        self.onboard()
        with patch.object(briefing,'local_inference',side_effect=TimeoutError('PRIVATE-SECRET')):
            code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':'first-request-0001'})
        self.assertEqual(code,409); self.assertNotIn(b'PRIVATE-SECRET',body)
        failed=briefing.latest(); self.assertEqual(failed['generation_status'],'failed')
        with patch.object(briefing,'local_inference',side_effect=result): retried=self.generate()
        self.assertEqual(failed['id'],retried['id'])
        self.assertEqual(len(briefing.history()),1)

    def test_interrupted_generation_requires_explicit_retry(self):
        self.onboard()
        with patch.object(briefing,'local_inference',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): briefing.generate('first-request-0001')
        self.assertEqual(briefing.latest()['generation_status'],'generating')
        briefing.recover_interrupted()
        self.assertEqual(briefing.latest()['generation_status'],'failed')
        with patch.object(briefing,'local_inference',side_effect=result): self.generate()
        self.assertEqual(len(briefing.history()),1)

    def test_profile_and_onboarding_are_transactional(self):
        self.onboard()
        before=briefing.read_profile()
        # Trigger simulates a write failure after the profile update but before commit.
        with briefing.database() as conn:
            conn.execute("CREATE TRIGGER reject_preferences BEFORE INSERT ON uhi_preferences BEGIN SELECT RAISE(ABORT,'disk full'); END")
        code,_,body=request('/api/onboarding/save','POST',data={'name':'Changed','niche':'Crafts'})
        self.assertEqual(code,400)
        self.assertEqual(briefing.read_profile(),before)
        self.assertTrue(server.get_onboarding_status()['onboarded'])

    def test_database_errors_are_honest(self):
        self.onboard()
        with patch.object(briefing.sqlite3,'connect',side_effect=sqlite3.OperationalError('PRIVATE-SECRET')):
            code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':'first-request-0001'})
        self.assertEqual(code,500); self.assertNotIn(b'PRIVATE-SECRET',body)
        self.assertIsNone(briefing.latest())
        briefing.DB_PATH.write_bytes(b'corrupted database')
        self.assertEqual(request('/api/creator/briefings')[0],500)

    def test_migrations_preserve_analytics_and_user_version(self):
        with closing(sqlite3.connect(briefing.DB_PATH)) as conn, conn:
            conn.execute('PRAGMA user_version=42')
            conn.execute('CREATE TABLE snapshots(id INTEGER PRIMARY KEY,date TEXT,platform TEXT,followers INTEGER,views INTEGER,engagement REAL,top_post TEXT)')
            conn.execute("INSERT INTO snapshots VALUES(1,'2026-01-01','youtube',NULL,NULL,NULL,'existing clip')")
            conn.execute('CREATE TABLE briefings(id INTEGER PRIMARY KEY,content TEXT)')
            conn.execute("INSERT INTO briefings VALUES(1,'existing briefing')")
        self.onboard()
        with patch.object(briefing,'local_inference',side_effect=result): self.generate()
        with closing(sqlite3.connect(briefing.DB_PATH)) as conn, conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],42)
            self.assertEqual(conn.execute('SELECT content FROM briefings').fetchone()[0],'existing briefing')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],1)
        self.assertIsNone(server.get_latest_snapshots()['youtube']['followers'])

    def test_serialize_inference_and_reject_bad_feedback(self):
        self.onboard()
        briefing.GENERATION_LOCK.acquire()
        try:
            with self.assertRaises(briefing.BriefingError): briefing.generate('first-request-0001')
        finally: briefing.GENERATION_LOCK.release()
        with patch.object(briefing,'local_inference',side_effect=result): first=self.generate()
        with self.assertRaises(ValueError): briefing.save_feedback(first['id'],'event-00000000001','answer','','automatically_done')
        with self.assertRaises(ValueError): briefing.save_feedback('unknown','event-00000000001','answer','','completed')
        self.assertEqual(briefing.latest()['completion_status'],'in_progress')

    def test_profile_updates_preserve_optional_fields(self):
        self.onboard(experience='Beginner',activities='Bake bread',available_time='Ten minutes')
        briefing.save_profile({'goals':'Make a bread clip'})
        self.assertEqual(briefing.read_profile()['available_time'],'Ten minutes')
        with patch.object(briefing,'local_inference',side_effect=result): row=self.generate()
        self.assertEqual(row['input_context']['creator_profile']['goals'],'Make a bread clip')

    def test_invalid_generation_output_is_not_success(self):
        self.onboard()
        with patch.object(briefing,'local_inference',return_value=({'recommended_action':'incomplete'},'mock')):
            code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':'first-request-0001'})
        self.assertEqual(code,409); self.assertEqual(briefing.latest()['generation_status'],'failed')

    def test_final_write_failure_never_claims_generated(self):
        self.onboard()
        with briefing.database() as conn:
            conn.execute("CREATE TRIGGER reject_generation BEFORE UPDATE OF content ON uhi_creator_briefings BEGIN SELECT RAISE(ABORT,'disk full'); END")
        with patch.object(briefing,'local_inference',side_effect=result):
            code,_,body=request('/api/creator/briefings/generate','POST',data={'request_id':'first-request-0001'})
        self.assertEqual(code,409)
        self.assertEqual(briefing.latest()['generation_status'],'failed')
        self.assertIsNone(briefing.latest()['content'])

    def test_feedback_write_failure_rolls_back_status(self):
        self.onboard()
        with patch.object(briefing,'local_inference',side_effect=result): first=self.generate()
        with briefing.database() as conn:
            conn.execute("CREATE TRIGGER reject_feedback BEFORE UPDATE OF user_response ON uhi_creator_briefings BEGIN SELECT RAISE(ABORT,'disk full'); END")
        code,_,body=request('/api/creator/briefings/feedback','POST',data={'briefing_id':first['id'],'event_id':'feedback-event-0001','response':'done','completion_status':'completed'})
        self.assertEqual(code,500)
        self.assertEqual(briefing.latest()['completion_status'],'in_progress')
        with briefing.database() as conn: self.assertEqual(conn.execute('SELECT COUNT(*) FROM uhi_creator_feedback').fetchone()[0],0)

if __name__=='__main__': unittest.main()
