"""Back up PostgreSQL, then apply checked-in SQL migrations transactionally."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from sqlalchemy import text, inspect
from database import engine

ROOT = Path(__file__).resolve().parent


def backup_database():
    target = ROOT.parent / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.dump')
    target.parent.mkdir(exist_ok=True)
    url = engine.url
    env = dict(os.environ, PGPASSWORD=url.password or '')
    binary = os.getenv('PG_DUMP', r'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe')
    subprocess.run([binary, '-h', url.host, '-p', str(url.port or 5432), '-U', url.username,
                    '-d', url.database, '-Fc', '-f', str(target)], env=env, check=True)
    restore = str(Path(binary).with_name('pg_restore.exe'))
    subprocess.run([restore, '--list', str(target)], check=True, stdout=subprocess.DEVNULL)
    print('Verified database backup:', target)
    return target


def migrate(backup=True):
    if backup:
        backup_database()
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(728104)'))
        if not inspect(conn).has_table('users'):
            import models
            models.Base.metadata.create_all(conn)
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())'))
        for file in sorted((ROOT / 'migrations').glob('*.sql')):
            sql = file.read_text(encoding='utf-8')
            digest = hashlib.sha256(sql.encode()).hexdigest()
            existing = conn.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'), {'v': file.name}).scalar()
            if existing:
                if existing != digest:
                    raise RuntimeError('Applied migration changed: ' + file.name)
                continue
            conn.exec_driver_sql(sql)
            conn.execute(text('INSERT INTO schema_migrations(version,checksum) VALUES (:v,:c)'), {'v':file.name,'c':digest})
            print('Applied:', file.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-backup', action='store_true', help='Only for disposable test databases')
    args = parser.parse_args()
    migrate(backup=not args.no_backup)
