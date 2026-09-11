"""Restore a real backup into an isolated test database and rehearse migration."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import engine
from migrate import backup_database
import psycopg
from psycopg import sql

root = Path(__file__).resolve().parents[1]
url = engine.url
backup = backup_database()
name = 'borrowbuddy_test_' + uuid.uuid4().hex[:10]
with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password, dbname='postgres', autocommit=True) as c:
    c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
env = dict(os.environ, PGPASSWORD=url.password or '', DB_NAME=name)
env.pop('DATABASE_URL', None)
subprocess.run([r'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe', '-h',url.host,'-p',str(url.port),'-U',url.username,'-d',name,'--no-owner','--no-privileges',str(backup)], env=env, check=True)
subprocess.run([sys.executable,'-B',str(root/'migrate.py'),'--no-backup'],env=env,check=True)
subprocess.run([sys.executable,'-B',str(root/'migrate.py'),'--no-backup'],env=env,check=True)
(root/'.test-database').write_text(name)
(root/'.test-backup').write_text(str(backup))
with psycopg.connect(host=url.host, port=url.port, user=url.username, password=url.password, dbname=name) as c:
    for table in ('users','resources','borrow_requests'):
        count=c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
        print('Preserved',table,count,'rows')
    print('Request statuses:',c.execute('SELECT status,count(*) FROM borrow_requests GROUP BY status').fetchall())
print('Migration rehearsal and repeat-run check passed:', name)
