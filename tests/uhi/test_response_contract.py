"""Output-contract tests; all model responses are fixtures, never real inference."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import test_isolation
from test_isolation import TEMP
import uhi_briefing as b
from test_inference import Response


def valid():
    return {
        'personal_context':'Alex enjoys vegetarian cooking, has ten minutes, and prefers not to show their face.',
        'recommended_action':'Record one ten-second hands-only clip mixing a chickpea salad.',
        'why':'It fits the saved ingredients and time, and adapts the skipped talking-head task to the saved feedback.',
        'steps':['Put your phone above the counter.','Record your hands mixing the salad.','Save the clip on your phone.'],
        'done_when':'Record and save one ten-second hands-only cooking video on your phone.',
        'question':'Would recording only your hands feel more comfortable?'
    }


class ResponseContractTests(unittest.TestCase):
    def setUp(self):
        for p in Path(TEMP.name).glob('*'):
            if p.is_file():p.unlink()
        self.env=patch.dict(os.environ,{'UHI_INFERENCE_APPROVED':'1','UHI_MODEL':'test:small','UHI_OLLAMA_URL':'http://127.0.0.1:11434'})
        self.env.start();self.addCleanup(self.env.stop)
        self.context={'creator_profile':{'identity':'Alex','niche':'Vegetarian cooking','available_time':'Ten minutes'},
                      'recent_briefings':[],
                      'learning_history':[{'response':'I prefer hands-only recording.','feedback':'I am not confident on camera.'}]}

    def test_complete_output_is_preserved_without_repairs(self):
        value=valid()
        self.assertIs(b.validate_output(value),value)
        self.assertEqual(b.parse_output(json.dumps(value)),value)
        self.assertIn('save one ten-second',value['done_when'])

    def test_missing_or_extra_fields_rejected(self):
        for field in b.BRIEFING_FIELDS:
            with self.subTest(field=field):
                value=valid();del value[field]
                with self.assertRaises(b.BriefingError):b.parse_output(json.dumps(value))
        value=valid();value['completion_status']='completed'
        with self.assertRaises(b.BriefingError):b.validate_output(value)

    def test_empty_whitespace_null_and_wrong_type_fields_rejected(self):
        for field in b.BRIEFING_FIELDS:
            for invalid in ('',' \t\n ',None,42,False,{}):
                with self.subTest(field=field,invalid=invalid):
                    value=valid();value[field]=[invalid] if field=='steps' else invalid
                    with self.assertRaises(b.BriefingError):b.validate_output(value)
        for invalid in ([],['one']*9,'not an array'):
            value=valid();value['steps']=invalid
            with self.assertRaises(b.BriefingError):b.validate_output(value)

    def test_original_empty_done_when_failure_is_still_rejected(self):
        value=valid();value['done_when']=''
        original=copy.deepcopy(value)
        with self.assertRaisesRegex(b.BriefingError,'done_when'):b.parse_output(json.dumps(value))
        self.assertEqual(value,original)
        self.assertEqual(value['done_when'],'')

    def test_malformed_response_and_duplicate_fields_rejected(self):
        for raw in ('{','', '[]','null','42','"a briefing"','```json\n{}\n```',
                    '{"done_when":"", "done_when":"secret replacement"}',
                    '{"done_when":NaN}', '{"done_when":Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(b.BriefingError):b.parse_output(raw)
        for raw in (None,{},b'{}'):
            with self.assertRaises(b.BriefingError):b.parse_output(raw)
        # Even a duplicate of a complete, valid field cannot silently overwrite it.
        raw=json.dumps(valid())[:-1]+',"done_when":"Already done"}'
        with self.assertRaisesRegex(b.BriefingError,'malformed'):b.parse_output(raw)

    def test_string_limits_remain_strict(self):
        for field in b.BRIEFING_FIELDS:
            value=valid();value[field]=['x'*4001] if field=='steps' else 'x'*4001
            with self.assertRaises(b.BriefingError):b.validate_output(value)

    def test_useful_beginner_question_topics_are_allowed(self):
        questions=[
            'Have you recorded a short video before?',
            'Would filming only your hands feel more comfortable?',
            'What got in the way of recording last time?',
            'Which everyday activity would you enjoy showing?',
            'How many minutes can you set aside tomorrow?'
        ]
        for question in questions:
            with self.subTest(question=question):
                value=valid();value['question']=question
                self.assertEqual(b.validate_output(value)['question'],question)

    def test_technical_questions_are_rejected_including_observed_failure(self):
        questions=[
            'What type of smartphone camera settings would you like to use for this task (e.g., HDR, low-light mode)?',
            'Which ISO would you choose?', 'What bitrate should the clip have?',
            'Which shutter speed do you prefer?', 'Do you prefer 4K or 1080p?',
            'Which codec would you use?', 'What frame rate should you set?'
        ]
        for question in questions:
            with self.subTest(question=question):
                value=valid();value['question']=question
                with self.assertRaisesRegex(b.BriefingError,'technical settings'):b.validate_output(value)

    def test_multiple_or_nonquestion_text_is_rejected(self):
        for question in ('How much time do you have? What interests you?',
                         'Tell me your camera settings.', 'How confident are you', '?'):
            value=valid();value['question']=question
            with self.assertRaises(b.BriefingError):b.validate_output(value)

    def test_prompt_schema_and_saved_feedback_reach_adapter(self):
        captured=[]
        def opened(request,timeout):
            if request.full_url.endswith('/api/ps'):return Response({'models':[{'name':'test:small'}]})
            captured.append((json.loads(request.data),timeout))
            return Response({'done':True,'message':{'content':json.dumps(valid())}})
        with patch('urllib.request.OpenerDirector.open',side_effect=opened):output,model=b.local_inference(self.context)
        self.assertEqual(output,valid());self.assertEqual(model,'test:small')
        payload,timeout=captured[0];schema=payload['format'];system=payload['messages'][0]['content']
        self.assertIsInstance(schema,dict)
        self.assertGreaterEqual(schema['properties']['done_when']['minLength'],1)
        self.assertEqual(json.loads(payload['messages'][1]['content']),self.context)
        self.assertIn('specific, observable completion criterion',system)
        self.assertIn('Adapt the criterion to the actual task',system)
        self.assertIn('do not re-ask details already answered',system)
        self.assertIn('Avoid technical setup questions',system)
        self.assertIn('If time is already known',system)
        self.assertEqual(timeout,90)

    def test_adapter_failures_persist_without_success_or_retries(self):
        b.save_profile({'niche':'Vegetarian cooking'})
        for index,raw in enumerate(('{',json.dumps(dict(valid(),done_when='')),
                                    json.dumps(dict(valid(),question='Which HDR mode do you prefer?')))):
            with self.subTest(raw=raw):
                with patch('urllib.request.OpenerDirector.open',side_effect=[
                    Response({'models':[{'name':'test:small'}]}),
                    Response({'done':True,'message':{'content':raw}})
                ]) as opened:
                    with self.assertRaises(b.BriefingError):b.generate('contract-failed-request-'+str(index))
                self.assertEqual(opened.call_count,2) # one status read + one mocked chat, no retry
                row=b.latest()
                self.assertEqual(row['generation_status'],'failed')
                self.assertIsNone(row['content'])
                self.assertTrue(row['error'])
                self.assertEqual(row['completion_status'],'in_progress')
        self.assertEqual(len(b.history()),3)

    def test_valid_structured_response_persists_exact_model_output(self):
        b.save_profile(self.context['creator_profile'])
        with patch('urllib.request.OpenerDirector.open', side_effect=[
            Response({'models':[{'name':'test:small'}]}),
            Response({'done':True,'message':{'content':json.dumps(valid())}})
        ]) as opened:
            generated = b.generate('valid-structured-response-request')
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(generated['generation_status'], 'generated')
        self.assertEqual(generated['content'], valid())
        self.assertEqual(generated['model'], 'test:small')
        self.assertEqual(generated['completion_status'], 'in_progress')
        self.assertEqual(b.latest()['content'], valid())

    def test_schema_unsupported_error_fails_closed_without_json_fallback(self):
        b.save_profile({'niche':'Vegetarian cooking'})
        error=HTTPError('http://127.0.0.1:11434/api/chat',400,'PRIVATE BACKEND DETAIL',None,None)
        with patch('urllib.request.OpenerDirector.open',side_effect=[
            Response({'models':[{'name':'test:small'}]}),error
        ]) as opened:
            with self.assertRaises(b.BriefingError) as raised:b.generate('unsupported-schema-request')
        self.assertEqual(opened.call_count,2)
        self.assertNotIn('PRIVATE',str(raised.exception))
        self.assertEqual(b.latest()['generation_status'],'failed')
        self.assertIsNone(b.latest()['content'])

if __name__=='__main__':unittest.main()
