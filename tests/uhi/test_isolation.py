import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

DASHBOARD = Path(__file__).resolve().parents[2] / 'dashboard'
sys.path.insert(0, str(DASHBOARD))
TEMP = tempfile.TemporaryDirectory(prefix='uhi-tests-')
os.environ['UHI_DATA_DIR'] = TEMP.name
import uhi_state
import server


class IsolationTests(unittest.TestCase):
    def setUp(self):
        for p in Path(TEMP.name).glob('*'):
            if p.is_file(): p.unlink()

    def test_no_shared_cron_or_telegram_actions(self):
        with patch('subprocess.run', side_effect=AssertionError('unexpected execution')):
            self.assertFalse(server.get_openclaw_cron_info()['found'])
            self.assertFalse(server.update_openclaw_cron('09:30')[0])
            self.assertFalse(server.test_telegram_bot_token('test-secret')[0])
            self.assertFalse(server.find_telegram_chat()[0])
            self.assertTrue(server.save_uhi_settings({'briefing_time':'09:30'})[0])
        self.assertFalse(server.get_uhi_settings()['cron_installed'])

    def test_setup_only_owned_directory(self):
        server.save_setup_state_to_disk({'version':'test'})
        self.assertEqual(json.loads((Path(TEMP.name)/'setup_state.json').read_text()), {'version':'test'})
        self.assertEqual(server.SETUP_STATE_PATH.parent, Path(TEMP.name).resolve())
        self.assertNotIn('ALT_SETUP_STATE_PATH', vars(server))

    def test_invalid_data_boundaries(self):
        for p in [uhi_state.SOURCE_ROOT, Path.home()/'.openclaw/other', Path.home()/'Togetherland/new', Path('relative'), Path.home()]:
            with self.assertRaises(ValueError): uhi_state.validate_data_dir(str(p))
        with tempfile.TemporaryDirectory() as d:
            alias=Path(d)/'alias'; alias.symlink_to(uhi_state.SOURCE_ROOT, target_is_directory=True)
            with self.assertRaises(ValueError): uhi_state.validate_data_dir(str(alias))

    def test_settings_persistence_errors_and_corruption(self):
        with patch('uhi_briefing.write_preferences', side_effect=OSError('failed')):
            self.assertFalse(server.save_uhi_settings({'model':'ollama/test'})[0])
        self.assertFalse(server.save_uhi_settings({'telegram_enabled':True})[0])
        (Path(TEMP.name)/'settings.json').write_text('{')
        with self.assertRaises(ValueError): uhi_state.load_settings()

    def test_symlinked_database_and_sidecar_cannot_escape(self):
        import uhi_briefing
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'protected.db'; target.write_bytes(b'protected data')
            for suffix in ('','-journal','-wal','-shm'):
                alias=Path(str(uhi_briefing.DB_PATH)+suffix)
                alias.symlink_to(target)
                try:
                    with self.assertRaises(ValueError):
                        with uhi_briefing.database(): pass
                    self.assertEqual(target.read_bytes(),b'protected data')
                finally: alias.unlink()

    def test_legacy_scripts_are_absent(self):
        self.assertFalse((DASHBOARD.parent/'scripts').exists())
        self.assertFalse((DASHBOARD/'manual.py').exists())

    def test_disabled_delivery_never_reads_credentials(self):
        with patch('subprocess.run', side_effect=AssertionError('credential access')):
            self.assertEqual(server.get_stored_telegram_token(), '')
            specs=server.get_system_specs()
            self.assertIsNone(specs['ram_gb'])

    def test_legacy_database_readers_reject_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'fixture.db'
            target.write_bytes(b'fixture only')
            alias=Path(TEMP.name)/'legacy-alias.db'
            alias.symlink_to(target)
            try:
                with patch.object(server, 'DB_PATH', alias):
                    for reader in (server.get_latest_snapshots, server.get_latest_briefing,
                                   server.get_snapshot_counts, server.clear_old_snapshots):
                        with self.assertRaises(ValueError): reader()
                self.assertEqual(target.read_bytes(), b'fixture only')
            finally:
                alias.unlink()

    def test_no_existing_user_data_imported(self):
        self.assertEqual(server.get_latest_snapshots(), {})
        self.assertEqual(server.get_profile_data()['identity'], '')
        self.assertFalse(server.get_onboarding_status()['onboarded'])

if __name__ == '__main__': unittest.main()
