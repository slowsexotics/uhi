import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_isolation
from test_isolation import server, uhi_state, TEMP, DASHBOARD
from http_fixture import request

class SecurityTests(unittest.TestCase):
    def setUp(self):
        for p in Path(TEMP.name).glob('*'):
            if p.is_file(): p.unlink()

    def test_full_dashboard_page_loads_with_real_setup_state(self):
        with patch.object(server, 'get_system_specs', return_value={}):
            code, headers, body = request('/', authenticated=False)
        self.assertEqual(code, 200)
        self.assertIn(b'window.INITIAL_SETUP_STATE', body)
        self.assertIn(b'creator-briefing-card', body)
        self.assertIn('Set-Cookie: uhi_session=', headers)
        self.assertEqual(request('/api/setup-state')[0], 200)

    def test_session_host_origin_and_csrf(self):
        self.assertEqual(request('/api/profile',authenticated=False)[0],401)
        self.assertEqual(request('/api/profile',headers={'Host':'evil.test:18080'})[0],403)
        self.assertEqual(request('/api/profile',headers={'Origin':'https://evil.test'})[0],403)
        self.assertEqual(request('/',authenticated=False,headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(request('/api/profile','POST',data={},csrf=False)[0],403)
        self.assertEqual(request('/api/profile','POST',data={},headers={'Origin':'null'})[0],403)
        code, headers, body=request('/api/profile')
        self.assertEqual(code,200)
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertIn('X-Content-Type-Options: nosniff',headers)
        self.assertEqual(request('/api/profile','OPTIONS')[0],405)

    def test_traversal_encoding_and_symlinks(self):
        for path in ['/assets/../server.py','/assets/%2e%2e/server.py','/assets/%2e%2e/%2e%2e/uhi_config.yaml','/screenshots/../../uhi_config.yaml','/assets/%00.png','/assets//etc/passwd']:
            self.assertIn(request(path)[0],(404,500))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'dashboard/assets').mkdir(parents=True)
            secret=root/'private.png'; secret.write_bytes(b'PRIVATE')
            (root/'dashboard/assets/leak.png').symlink_to(secret)
            with patch.object(server,'BASE_DIR',root):
                self.assertEqual(request('/assets/leak.png')[0],404)
                (root/'dashboard/assets/ok.png').write_bytes(b'IMAGE')
                code,_,body=request('/assets/ok.png'); self.assertEqual((code,body),(200,b'IMAGE'))

    def test_xss_bootstrap_escaped(self):
        malicious='</script><script>alert("profile")</script>\u2028&'
        with patch.object(server,'get_system_specs',return_value={}), patch.object(server,'get_onboarding_status',return_value={'profile':{'identity':malicious}}), patch.object(server,'get_setup_state',return_value={}):
            code,headers,body=request('/',authenticated=False)
        self.assertEqual(code,200)
        self.assertNotIn(malicious.encode(),body)
        self.assertIn(b'\\u003c/script\\u003e',body)
        self.assertIn('HttpOnly; SameSite=Strict',headers)

    def test_malformed_and_oversized_requests(self):
        for body in [b'[]',b'{',b'null']:
            self.assertEqual(request('/api/profile','POST',raw_body=body)[0],400)
        self.assertEqual(request('/api/profile','POST',headers={'Content-Length':'-1'})[0],400)
        self.assertEqual(request('/api/profile','POST',headers={'Content-Length':'65537'})[0],400)
        self.assertEqual(request('/api/profile','POST',headers={'Content-Type':'text/plain'})[0],400)
        self.assertEqual(request('/api/profile','POST',headers={'Transfer-Encoding':'chunked'})[0],400)

    def test_failed_persistence_and_disabled_integrations(self):
        with patch('uhi_briefing.sqlite3.connect',side_effect=OSError('PRIVATE-SECRET')):
            with contextlib.redirect_stderr(io.StringIO()):
                code,_,body=request('/api/profile','POST',data={'identity':'Alex'})
            self.assertEqual(code,500); self.assertNotIn(b'PRIVATE-SECRET',body)
        with patch('urllib.request.urlopen',side_effect=AssertionError('external access')), patch('subprocess.Popen',side_effect=AssertionError('service start')):
            for path in ['/api/ai/setup-runtime','/api/telegram/test-bot','/api/telegram/find-chat','/api/accounts/test']:
                self.assertEqual(request(path,'POST')[0],409)
            self.assertFalse(server.get_local_ai_status()['ready'])
        self.assertEqual(request('/api/onboarding/save','POST',data={'api_key':'secret','model':'openai/test'})[0],400)
        self.assertFalse((uhi_state.DATA_DIR/'ai_keys.json').exists())

    def test_malicious_creator_input_is_data_and_never_a_shell_command(self):
        import uhi_briefing
        from test_beginner import result
        value = "Cooking'; $(touch /tmp/never-create-uhi); --"
        uhi_briefing.save_profile({'niche':value})
        seen=[]
        def infer(context):
            seen.append(context['creator_profile']['niche'])
            return result(context)
        with patch('subprocess.run',side_effect=AssertionError('unexpected execution')):
            uhi_briefing.generate('malicious-input-0001',infer=infer)
        self.assertEqual(seen,[value])


if __name__=='__main__': unittest.main()
