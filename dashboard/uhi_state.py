"""Small UHI-owned storage boundary. Never discovers OpenClaw state."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

SOURCE_ROOT = Path(__file__).resolve().parent.parent
INSTALLATION_ID = hashlib.sha256(str(SOURCE_ROOT).encode()).hexdigest()[:16]
DEFAULT_DIR = Path.home() / 'Library' / 'Application Support' / 'UHI' / INSTALLATION_ID


def validate_data_dir(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('UHI_DATA_DIR must be absolute.')
    resolved = path.resolve()
    protected = [SOURCE_ROOT, Path.home() / '.openclaw', Path.home() / 'Togetherland']
    for root in protected:
        root = root.resolve()
        if resolved == root or root in resolved.parents or resolved in root.parents:
            raise ValueError('UHI data must be outside protected source and OpenClaw paths.')
    if resolved.exists() and not resolved.is_dir():
        raise ValueError('UHI_DATA_DIR must be a directory.')
    return resolved


DATA_DIR = validate_data_dir(os.environ.get('UHI_DATA_DIR', str(DEFAULT_DIR)))
KEYCHAIN_SERVICE = 'UHI.' + INSTALLATION_ID
DEFAULTS = {'onboarded': False, 'timezone': 'America/Detroit', 'briefing_time': '08:30',
            'model': '', 'telegram_enabled': False, 'telegram_target': ''}


def owned_file(path):
    path = Path(path)
    if path.parent != DATA_DIR or path.is_symlink() or path.resolve().parent != DATA_DIR:
        raise ValueError('UHI state file is outside its owned directory.')
    if DATA_DIR.resolve() != DATA_DIR:
        raise ValueError('UHI data directory changed after configuration.')
    return path


def atomic_json(path, value):
    path = owned_file(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.uhi-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_settings():
    path = owned_file(DATA_DIR / 'settings.json')
    from uhi_briefing import read_preferences
    saved = read_preferences()
    if saved:
        return dict(DEFAULTS, **saved)
    if not path.exists():
        return dict(DEFAULTS)
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('UHI settings are corrupted.')
    return dict(DEFAULTS, **data)


def save_settings(updates):
    if not isinstance(updates, dict) or set(updates) - set(DEFAULTS):
        raise ValueError('Unknown UHI preference.')
    data = load_settings()
    for key, value in updates.items():
        if key in ('onboarded', 'telegram_enabled'):
            if type(value) is not bool:
                raise ValueError('Expected boolean.')
        elif not isinstance(value, str) or len(value) > 200 or '\n' in value:
            raise ValueError('Invalid preference.')
        if key == 'model' and value:
            import re
            if not re.fullmatch(r'ollama/[A-Za-z0-9_.:/-]{1,150}', value):
                raise ValueError('Only explicitly configured local inference is supported.')
        if key == 'timezone':
            try:
                ZoneInfo(value)
            except (KeyError, ValueError):
                raise ValueError('Invalid timezone.') from None
        if key == 'briefing_time':
            from datetime import time
            time.fromisoformat(value)
        if key == 'telegram_enabled' and value:
            raise ValueError('Isolated Telegram delivery has not been configured.')
        data[key] = value
    from uhi_briefing import write_preferences
    write_preferences(data)
    return data


def keychain_get(account):
    # Delivery is disabled in the public preview; never query host credentials.
    return ''


def keychain_set(account, secret):
    # Credential writes are deliberately unavailable until isolated delivery is approved.
    # This avoids secrets in argv, subprocess diagnostics, and plaintext files.
    return False
