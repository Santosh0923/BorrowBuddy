"""Create disposable browser-review accounts only in the isolated test DB."""
from pathlib import Path
import os
import sys
import json
import secrets

root=Path(__file__).resolve().parents[1]
name=(root/'.test-database').read_text().strip()
assert name.startswith('borrowbuddy_test_')
os.environ['DB_NAME']=name
os.environ.pop('DATABASE_URL',None)
sys.path.insert(0,str(root))
from database import SessionLocal,engine
from auth import hash_password
import models

password=secrets.token_urlsafe(18)
accounts={}
with SessionLocal() as db:
    for role in ('student','faculty','admin'):
        user=models.User(name='Review '+role.title(),email='review-'+role+'-'+secrets.token_hex(3)+'@university.test',password_hash=hash_password(password),role=role)
        db.add(user);db.flush()
        accounts[role]={'email':user.email,'password':password,'id':user.id}
    db.commit()
(root/'.test-browser.json').write_text(json.dumps(accounts))
engine.dispose()
print('Disposable browser accounts prepared in',name)
