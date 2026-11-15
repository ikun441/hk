import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True, mode=0o700)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA / "crm.sqlite3"}')
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
SESSION_HOURS = int(os.getenv('SESSION_HOURS', '8'))

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
