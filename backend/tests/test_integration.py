"""HTTP + PostgreSQL integration tests against a restored, disposable database."""
import concurrent.futures
from datetime import date, timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
name = (ROOT / '.test-database').read_text().strip()
if not name.startswith('borrowbuddy_test_'):
    raise RuntimeError('Integration tests require an isolated test database')
os.environ['DB_NAME'] = name
os.environ.pop('DATABASE_URL', None)
sys.path.insert(0, str(ROOT))
from database import SessionLocal, engine
from auth import hash_password, create_access_token
from sqlalchemy import text
import models

BASE = 'http://127.0.0.1:8002'


def call(path, token=None, method='GET', body=None, form=False):
    headers = {}
    data = None
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
    req = urllib.request.Request(BASE + path, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, json.loads(exc.read())


class BorrowBuddyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(20)
        cls.users = {}
        with SessionLocal() as db:
            for key, role in [('admin','admin'),('faculty','faculty'),('staff','faculty'),('student','student'),('other','student')]:
                u = models.User(name='Test '+key, email=secrets.token_hex(7)+'@test.invalid', role=role, password_hash=hash_password(cls.password))
                db.add(u); db.flush()
                cls.users[key] = {'id':u.id,'email':u.email,'role':role}
            db.commit()
        cls.log = open(ROOT/'.test-server.log', 'w', encoding='utf-8')
        cls.server = subprocess.Popen([sys.executable,'-B','-m','uvicorn','main:app','--host','127.0.0.1','--port','8002'], cwd=ROOT, env=os.environ.copy(), stdout=cls.log, stderr=cls.log)
        for _ in range(100):
            try:
                if call('/health')[0] == 200: break
            except OSError: pass
            if cls.server.poll() is not None: raise RuntimeError('Test server failed; see .test-server.log')
            time.sleep(.1)
        else: raise RuntimeError('Test server did not start')
        cls.tokens = {}
        for key,u in cls.users.items():
            status, data = call('/auth/login', method='POST', body={'username':u['email'],'password':cls.password},form=True)
            assert status == 200, data
            cls.tokens[key] = data['access_token']

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate(); cls.server.wait(timeout=15); cls.log.close()
        engine.dispose()

    def req(self, path, who='admin', method='GET', body=None, expected=200):
        status, data = call(path,self.tokens[who],method,body)
        self.assertEqual(status,expected,(path,data))
        return data

    def resource(self, quantity=3, custodian='faculty'):
        r = self.req('/resources',custodian,'POST',{'name':'Test item '+secrets.token_hex(5),'category':'Electronics','location':'Test lab','quantity':quantity})
        return self.req(f"/resources/{r['id']}/verify",method='POST',body={'decision':'Verified'})

    def request(self, resource, who='student', quantity=1):
        return self.req('/requests',who,'POST',{'resource_id':resource['id'],'quantity':quantity,'return_date':str(date.today()+timedelta(days=4)),'purpose':'Integration verification'})

    def action(self, request, action, who='faculty', body=None, expected=200):
        return self.req(f"/requests/{request['id']}/{action}",who,'PATCH' if action=='cancel' else 'POST',body,expected)

    def to_inspection(self, request):
        for action in ('approve','ready','collect','return'): self.action(request,action)

    def test_01_auth_and_registration(self):
        self.assertEqual(call('/auth/me')[0],401)
        self.assertEqual(call('/resources')[0],401)
        self.assertEqual(call('/auth/login',method='POST',body={'username':'nobody@test.invalid','password':'bad'},form=True)[0],401)
        invalid=create_access_token('not-an-integer','a@test.invalid','admin')
        self.assertEqual(call('/auth/me',invalid)[0],401)
        self.req('/admin/users','student',expected=403)
        self.req('/resources','student','POST',{'name':'Forbidden','category':'x','location':'x','quantity':1},403)
        code,_=call('/auth/register',method='POST',body={'name':' ','email':'invalid','password':'short'})
        self.assertEqual(code,422)
        email=secrets.token_hex(7)+'@test.invalid'
        code,data=call('/auth/register',method='POST',body={'name':'New student','email':email,'password':self.password,'role':'admin'})
        self.assertEqual(code,200); self.assertEqual(data['role'],'student')

    def test_02_full_lifecycle_and_history(self):
        r=self.resource(3); q=self.request(r,quantity=2)
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],3)
        self.action(q,'approve')
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],1)
        for action in ('ready','collect','return'): self.action(q,action)
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],1)
        done=self.action(q,'inspect',body={'condition':'Good','notes':'All checked'})
        self.assertEqual(done['status'],'Completed'); self.assertEqual(done['inspected_by'],self.users['faculty']['id'])
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],3)
        history=self.req(f"/requests/{q['id']}/history",'student')
        self.assertEqual(len(history),6)
        self.assertEqual(history[0]['action_by_user_id'],self.users['student']['id'])
        self.assertTrue(all(h['action_by_user_id']==self.users['faculty']['id'] for h in history[1:]))
        self.action(q,'inspect',body={'condition':'Good'},expected=409)

    def test_03_custody_and_ownership(self):
        q=self.request(self.resource())
        for role in ('staff','admin','student'):
            for action in ('approve','ready','collect','return','inspect','complete-maintenance'):
                self.action(q,action,role,{'condition':'Good'} if action=='inspect' else None,403)
        self.action(q,'cancel','staff',expected=403)
        self.req(f"/requests/{q['id']}",'other',expected=403)
        self.req(f"/requests/{q['id']}/history",'staff',expected=403)
        self.assertFalse(any(r['id']==q['id'] for r in self.req('/requests','other')))
        self.assertFalse(any(r['id']==q['id'] for r in self.req('/requests','staff')))

    def test_04_cancellation_and_no_deletion(self):
        r=self.resource(2); q=self.request(r)
        self.action(q,'cancel','student')
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],2)
        q=self.request(r); self.action(q,'approve')
        self.action(q,'cancel','student',expected=400)
        self.action(q,'cancel','faculty')
        self.action(q,'cancel','faculty',expected=400)
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],2)
        self.req(f"/requests/{q['id']}",method='DELETE',expected=409)

    def test_05_maintenance_and_bypass(self):
        r=self.resource(2); q=self.request(r)
        self.to_inspection(q)
        self.action(q,'complete-maintenance',expected=409)
        self.action(q,'inspect',body={'condition':'Minor Damage','notes':'Repair needed'})
        self.action(q,'complete-maintenance','staff',expected=403)
        self.assertEqual(self.req(f"/resources/{r['id']}")['maintenance_quantity'],1)
        self.action(q,'complete-maintenance',body={'notes':'Repaired','restore_quantity':True})
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],2)
        q=self.request(r); self.to_inspection(q)
        self.action(q,'inspect',body={'condition':'Major Damage','notes':'Unrepairable'})
        self.action(q,'complete-maintenance',body={'notes':'Disposed','restore_quantity':False})
        result=self.req(f"/resources/{r['id']}")
        self.assertEqual((result['total_quantity'],result['available_quantity']),(1,1))

    def test_06_inventory_adjustments(self):
        r=self.resource(4); q=self.request(r,quantity=2); self.action(q,'approve')
        path=f"/resources/{r['id']}/adjust"
        self.req(path,method='PATCH',body={'total_quantity':1,'reason':'Invalid shrink'},expected=409)
        self.req(path,method='PATCH',body={'available_quantity':3,'reason':'Would oversell'},expected=409)
        self.req(path,method='PATCH',body={'available_quantity':-1,'reason':'Negative'},expected=409)
        self.req(path,method='PATCH',body={'available_quantity':1,'reason':'  '},expected=422)
        self.req(path,method='PATCH',body={'total_quantity':5,'available_quantity':3,'reason':'New stock'})
        events=self.req('/admin/audit?entity_type=resource')['items']
        self.assertTrue(any(e['entity_id']==r['id'] and e['details'].get('reason')=='New stock' for e in events))

    def test_07_concurrent_approval(self):
        r=self.resource(1); a=self.request(r); b=self.request(r,'other')
        def approve(q): return call(f"/requests/{q['id']}/approve",self.tokens['faculty'],'POST')[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(approve,[a,b]))
        self.assertEqual(sorted(results),[200,400])
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],0)
        r=self.resource(3); q=self.request(r)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(approve,[q,q]))
        self.assertEqual(sorted(results),[200,400])
        self.assertEqual(self.req(f"/resources/{r['id']}")['available_quantity'],2)

    def test_08_assignment_transfer(self):
        r=self.resource(); q=self.request(r)
        self.req(f"/resources/{r['id']}",method='PATCH',body={'custodian_id':self.users['staff']['id']})
        self.action(q,'approve','faculty',expected=403)
        self.action(q,'approve','staff')
        self.assertEqual(self.req(f"/requests/{q['id']}")['custodian_id'],self.users['staff']['id'])
        self.req(f"/resources/{r['id']}",method='PATCH',body={'custodian_id':None},expected=409)
        self.req(f"/requests/{q['id']}/custodian",method='PATCH',body={'custodian_id':self.users['faculty']['id'],'reason':'Coverage transfer'},expected=409)
        self.req(f"/resources/{r['id']}",method='PATCH',body={'custodian_id':self.users['faculty']['id']})
        self.action(q,'ready','faculty')

    def test_09_retirement_maintenance_and_unassigned(self):
        r=self.resource(); self.req(f"/resources/{r['id']}",method='PATCH',body={'status':'Maintenance'})
        self.req('/requests','student','POST',{'resource_id':r['id'],'return_date':str(date.today()),'purpose':'Verification test'},409)
        self.req(f"/resources/{r['id']}",method='PATCH',body={'status':'Available'})
        q=self.request(r)
        self.req(f"/resources/{r['id']}",method='DELETE',expected=409)
        self.action(q,'cancel','student')
        self.req(f"/resources/{r['id']}",method='DELETE')
        self.assertFalse(any(x['id']==r['id'] for x in self.req('/resources','student')))
        self.assertTrue(any(x['id']==r['id'] for x in self.req('/resources?include_retired=true')))
        self.req(f"/resources/{r['id']}",method='PATCH',body={'is_active':True,'status':'Available'})
        self.req(f"/resources/{r['id']}",method='PATCH',body={'custodian_id':None})
        self.req('/requests','student','POST',{'resource_id':r['id'],'return_date':str(date.today()),'purpose':'Verification test'},409)

    def test_10_user_management(self):
        u=self.req('/admin/users',method='POST',body={'name':'Managed user','email':secrets.token_hex(7)+'@test.invalid','password':self.password,'role':'faculty'})
        self.req(f"/admin/users/{u['id']}/role",method='PATCH',body={'role':'faculty'})
        self.req(f"/admin/users/{u['id']}/toggle-active",method='PATCH')
        token=create_access_token(u['id'],u['email'],'admin')
        self.assertEqual(call('/auth/me',token)[0],403)
        self.req(f"/admin/users/{u['id']}/toggle-active",method='PATCH')
        self.assertEqual(call('/admin/users',token)[0],403)  # DB role wins over token claim
        self.req(f"/admin/users/{self.users['admin']['id']}/role",method='PATCH',body={'role':'student'},expected=400)
        self.req(f"/admin/users/{self.users['faculty']['id']}/toggle-active",method='PATCH',expected=409)

    def test_11_history_append_only(self):
        q=self.request(self.resource()); self.action(q,'reject',body={'rejection_reason':'Not available for this use'})
        with engine.connect() as c:
            with self.assertRaises(Exception): c.execute(text('DELETE FROM request_history WHERE request_id=:id'),{'id':q['id']})
            c.rollback()
            with self.assertRaises(Exception): c.execute(text("UPDATE audit_events SET action='Changed'"))
            c.rollback()

    def test_12_invalid_payloads_and_transitions(self):
        self.req('/resources','faculty',method='POST',body={'name':'Legacy','category':'x','location':'x','total_quantity':9,'available_quantity':9},expected=422)
        r=self.resource(); q=self.request(r)
        self.action(q,'collect',expected=400)
        self.action(q,'reject',body={'rejection_reason':' '},expected=422)
        self.action(q,'inspect',body={'condition':'Good'},expected=409)
        self.req(f"/resources/{r['id']}",method='PATCH',body={'name':None},expected=422)
        self.req(f"/resources/{r['id']}",method='PATCH',body={'status':'Bogus'},expected=422)
        self.req('/requests','student','POST',{'resource_id':r['id'],'quantity':0,'return_date':str(date.today()),'purpose':'Verification test'},expected=422)

    def test_13_database_inventory_invariants(self):
        with engine.connect() as c:
            invalid=c.execute(text("SELECT count(*) FROM resources r WHERE available_quantity<0 OR total_quantity<available_quantity OR available_quantity + coalesce((SELECT sum(quantity) FROM borrow_requests b WHERE b.resource_id=r.id AND b.status IN ('Approved','Ready for Pickup','Collected','Returned Pending Inspection','Maintenance Required')),0)>total_quantity")).scalar()
            self.assertEqual(invalid,0)

    def test_14_faculty_submission_and_admin_verification(self):
        r=self.req('/resources','faculty','POST',{'name':'Pending '+secrets.token_hex(6),'category':'Academic','description':'Owned listing','location':'Library','quantity':4})
        self.assertEqual(r['verification_status'],'Pending Verification')
        self.assertEqual(r['custodian_id'],self.users['faculty']['id'])
        self.assertFalse(any(x['id']==r['id'] for x in self.req('/resources','student')))
        self.req(f"/resources/{r['id']}",'student',expected=403)
        self.req('/requests','student','POST',{'resource_id':r['id'],'quantity':1,'purpose':'Study','return_date':str(date.today()+timedelta(days=3))},403)
        self.assertTrue(any(x['id']==r['id'] for x in self.req('/resources?verification_status=Pending%20Verification')))
        self.req(f"/resources/{r['id']}/verify",'faculty','POST',{'decision':'Verified'},403)
        self.req(f"/resources/{r['id']}/verify",'student','POST',{'decision':'Verified'},403)
        r=self.req(f"/resources/{r['id']}/verify",method='POST',body={'decision':'Verified'})
        self.assertTrue(any(x['id']==r['id'] for x in self.req('/resources','student')))
        q=self.request(r)
        self.assertEqual(q['custodian_id'],self.users['faculty']['id'])
        self.assertTrue(any(x['id']==q['id'] for x in self.req('/requests','faculty')))
        self.assertFalse(any(x['id']==q['id'] for x in self.req('/requests','staff')))
        self.action(q,'approve')

    def test_15_rejection_and_resubmission(self):
        r=self.req('/resources','faculty','POST',{'name':'Reject '+secrets.token_hex(6),'category':'Academic','location':'Library','quantity':2})
        path=f"/resources/{r['id']}/verify"
        self.req(path,method='POST',body={'decision':'Rejected','reason':' '},expected=422)
        r=self.req(path,method='POST',body={'decision':'Rejected','reason':'Clarify equipment condition'})
        self.assertEqual(r['verification_status'],'Rejected')
        self.assertEqual(r['verification_reason'],'Clarify equipment condition')
        self.req(f"/resources/{r['id']}",'student',expected=403)
        self.req(f"/resources/{r['id']}/resubmit",'staff','POST',expected=403)
        r=self.req(f"/resources/{r['id']}/resubmit",'faculty','POST')
        self.assertEqual(r['verification_status'],'Pending Verification')

    def test_16_faculty_owner_boundaries(self):
        r=self.resource()
        self.req(f"/resources/{r['id']}",'staff',expected=403)
        self.assertFalse(any(x['id']==r['id'] for x in self.req('/resources','staff')))
        self.req(f"/resources/{r['id']}",'staff','PATCH',{'description':'Not mine'},403)
        self.req(f"/resources/{r['id']}",'faculty','PATCH',{'custodian_id':self.users['staff']['id']},403)
        self.req(f"/resources/{r['id']}",'faculty','PATCH',{'status':'Retired'},403)
        self.req(f"/resources/{r['id']}/adjust",'faculty','PATCH',{'total_quantity':10,'reason':'Not allowed'},403)
        self.req('/resources','faculty','POST',{'name':'Spoof','category':'x','location':'x','quantity':1,'custodian_id':self.users['staff']['id']},422)
        self.req('/resources',method='POST',body={'name':'Admin listing','category':'x','location':'x','quantity':1},expected=403)

    def test_17_replenishment_and_reverification(self):
        r=self.resource(3)
        self.req(f"/resources/{r['id']}/replenish",'staff','POST',{'quantity':2},403)
        result=self.req(f"/resources/{r['id']}/replenish",'faculty','POST',{'quantity':2})
        self.assertEqual((result['total_quantity'],result['available_quantity']),(5,5))
        self.assertEqual(result['verification_status'],'Verified')
        result=self.req(f"/resources/{r['id']}",'faculty','PATCH',{'description':'Updated listing details'})
        self.assertEqual(result['verification_status'],'Pending Verification')
        self.req(f"/resources/{r['id']}",'student',expected=403)

    def test_18_only_three_current_roles(self):
        self.req('/admin/users',method='POST',body={'name':'Invalid role','email':secrets.token_hex(6)+'@test.invalid','password':self.password,'role':'staff'},expected=422)
        self.req(f"/admin/users/{self.users['other']['id']}/role",method='PATCH',body={'role':'staff'},expected=422)
        self.req('/dashboard/admin','faculty',expected=403)
        self.req('/dashboard/faculty','student',expected=403)
        self.req('/dashboard/student','faculty',expected=403)
        self.req('/admin/users/faculty','student',expected=403)

    def test_19_purpose_required(self):
        r=self.resource()
        self.req('/requests','student','POST',{'resource_id':r['id'],'quantity':1,'return_date':str(date.today()+timedelta(days=2)),'purpose':'   '},422)

    def test_21_unchanged_listing_preserves_verification(self):
        for decision in ('Verified', 'Rejected'):
            resource = self.req('/resources', 'faculty', 'POST', {'name':'No-op '+secrets.token_hex(6),'category':'Academic','location':'Library','quantity':2})
            reviewed = self.req(f"/resources/{resource['id']}/verify", method='POST', body={'decision':decision,'reason':'Review decision'})
            saved = self.req(f"/resources/{resource['id']}", method='PATCH', body={'name':' '+resource['name']+' ','category':resource['category'],'location':resource['location'],'description':'','custodian_id':resource['custodian_id'],'status':'Available','is_active':True})
            for key in ('verification_status','verification_reason','verified_by','verified_at','description','available_quantity'):
                self.assertEqual(saved[key], reviewed[key], key)
            self.assertIsNone(saved['description'])
            edited = self.req(f"/resources/{resource['id']}", method='PATCH', body={'description':'A genuinely changed listing'})
            self.assertEqual(edited['verification_status'], 'Pending Verification')
            self.assertIsNone(edited['verified_by'])

    def test_20_owner_identity(self):
        fields={'name':'Shared name '+secrets.token_hex(5),'category':'Academic','location':'Shared room','quantity':2}
        a=self.req('/resources','faculty','POST',fields)
        b=self.req('/resources','staff','POST',fields)
        self.assertNotEqual(a['custodian_id'],b['custodian_id'])


if __name__ == '__main__': unittest.main(verbosity=2)
