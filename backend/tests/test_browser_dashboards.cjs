// Dashboard-only checks. Live requests are read-only; mutations use browser API fixtures.
const { chromium, expect } = require('playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const snapshots = JSON.parse(fs.readFileSync(path.join(__dirname, '../.test-dashboard-live.json'), 'utf8'));
const site = 'http://127.0.0.1:5173';
const labels = {
  admin: ['Listings awaiting verification','Total inventory','Available inventory','Issued / reserved','Exceptions','Active users'],
  faculty: ['My active resource listings','My available resource units','Pending student requests','Ready for pickup','Currently issued','Awaiting return confirmation'],
  student: ['Available resources','Active requests','Ready for pickup','Currently borrowed','Due soon / overdue','Completed borrows'],
};
async function cards(page, role, values) {
  await expect(page.locator('.stat')).toHaveCount(6);
  for (let i=0;i<6;i++) {
    const card = page.locator('.stat').filter({has:page.locator('.stat-label',{hasText:new RegExp('^'+labels[role][i]+'$')})});
    await expect(card.locator('strong')).toHaveText(String(values[i]));
  }
}
(async()=>{
  const { inventoryMetrics, overviewData } = await import(pathToFileURL(path.resolve(__dirname,'../../frontend/src/dashboardMetrics.js')));
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const errors=[];
  try {
    for (const snapshot of snapshots.filter(s=>!process.env.DASHBOARD_ROLE || s.user.role===process.env.DASHBOARD_ROLE)) {
      const page=await browser.newPage(); page.on('pageerror',e=>errors.push(e.message));
      await page.addInitScript(token=>localStorage.setItem('borrowbuddy_token',token),snapshot.token);
      await page.goto(site+'/'+snapshot.user.role+'/overview');
      const expected=snapshot.user.role==='admin'?[0,10,5,0,2,4]:snapshot.user.role==='student'?[1,0,0,0,0,1]:snapshot.user.id===3?[1,5,0,0,0,0]:[0,0,0,0,0,0];
      await cards(page,snapshot.user.role,expected); await page.reload(); await cards(page,snapshot.user.role,expected);
      console.log('PASS live database/API/browser + reload:',snapshot.user.role,snapshot.user.id,expected);
      await page.close();
    }
    for (const role of ['admin','faculty','student'].filter(r=>!process.env.DASHBOARD_ROLE || r===process.env.DASHBOARD_ROLE)) {
      const base=snapshots.find(s=>s.user.role===role);
      const owner=3, student=5;
      const resource={...snapshots[0].resources.find(r=>r.id===3),id:900,name:'Dashboard fixture',total_quantity:12,available_quantity:7,reserved_quantity:2,issued_quantity:1,inspection_quantity:1,maintenance_quantity:1,unavailable_quantity:0};
      const restricted={...resource,id:901,name:'Pending fixture',total_quantity:5,available_quantity:5,reserved_quantity:0,issued_quantity:0,inspection_quantity:0,maintenance_quantity:0,verification_status:'Pending Verification'};
      const other={...restricted,id:902,custodian_id:999,verification_status:'Verified',total_quantity:4,available_quantity:4};
      const retired={...other,id:903,total_quantity:99,available_quantity:99,is_active:false};
      const statuses=['Requested','Approved','Ready for Pickup','Collected','Returned Pending Inspection','Maintenance Required','Completed','Rejected','Cancelled'];
      const seed=snapshots.find(s=>s.user.role==='student').requests[0];
      const requests=statuses.map((status,i)=>({...seed,id:910+i,student_id:student,custodian_id:owner,resource_id:900,resource_name:resource.name,quantity:1,status,is_due_soon:status==='Collected',is_overdue:false}));
      requests.push({...requests[0],id:999,student_id:999,custodian_id:999});
      const state={...base,resources:[resource,restricted,other,retired],requests};
      assert.deepEqual(inventoryMetrics(state.resources),{total:21,available:11,reserved:2,issued:1,inspection:1,unavailable:6});
      if(role==='faculty') assert.deepEqual(inventoryMetrics(overviewData(state).resources),{total:17,available:7,reserved:2,issued:1,inspection:1,unavailable:6});
      const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
      let reads=0;
      await page.route('**/api/**',async route=>{
        const req=route.request(), url=new URL(req.url()), endpoint=url.pathname.slice(4);
        let result;
        if(req.method()==='POST'&&endpoint==='/requests/910/approve') {
          requests[0].status='Approved';resource.available_quantity--;resource.reserved_quantity++; result=requests[0];
        } else if(endpoint==='/auth/me') result=base.user;
        else if(endpoint==='/resources') result=state.resources;
        else if(endpoint==='/requests') {result=requests;reads++;}
        else if(endpoint.endsWith('/history')) result=[];
        else if(endpoint==='/admin/users') result=state.users;
        else if(endpoint==='/admin/users/faculty') result=[];
        else throw new Error('Unexpected dashboard API '+req.method()+' '+endpoint);
        await route.fulfill({json:result});
      });
      await page.addInitScript(()=>localStorage.setItem('borrowbuddy_token','dashboard-fixture'));
      await page.goto(site+'/'+role+'/overview');
      const expected=role==='admin'?[1,21,11,3,1,4]:role==='faculty'?[2,7,1,1,1,1]:[2,6,1,1,1,1];
      await cards(page,role,expected);
      if(role==='faculty') {
        await page.getByRole('button',{name:'Open request 910',exact:true}).click();
        await page.getByRole('button',{name:'Approve request',exact:true}).click();
        const before=reads;
        await page.getByRole('button',{name:'Confirm & save',exact:true}).click();
        await expect.poll(()=>reads).toBeGreaterThan(before);
        await page.getByRole('button',{name:'Close dialog',exact:true}).click();
        expected[1]=6;expected[2]=0;await cards(page,role,expected);
      }
      // A relevant external action updates the server fixture while another view is open.
      await page.getByRole('navigation').getByRole('button',{name:role==='admin'?'Inventory':role==='faculty'?'My Resources':'Browse Resources',exact:true}).click();
      if(role==='admin'){restricted.verification_status='Verified';expected[0]=0;expected[2]+=5;}
      if(role==='faculty'){requests[1].status='Ready for Pickup';expected[3]++;}
      if(role==='student'){requests[0].status='Rejected';expected[1]--;}
      await page.getByRole('navigation').getByRole('button',{name:'Overview',exact:true}).click();
      await cards(page,role,expected);
      // Refocusing Overview and browser reload must each fetch current metrics.
      if(role==='admin'){resource.available_quantity++;resource.total_quantity++;expected[1]++;expected[2]++;}
      if(role==='faculty'){requests[2].status='Collected';expected[3]--;expected[4]++;}
      if(role==='student'){requests[2].status='Collected';expected[2]--;expected[3]++;}
      await page.evaluate(()=>window.dispatchEvent(new Event('focus'))); await cards(page,role,expected);
      await page.reload();await cards(page,role,expected);
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.locator('.stat').evaluateAll(cards=>cards.every(card=>card.getBoundingClientRect().right<=innerWidth+1)));
      console.log('PASS scoped status fixtures, inventory reconciliation, Overview navigation/focus/reload:',role);
      await page.close();
    }
    assert.deepEqual(errors,[]);console.log('PASS no dashboard runtime errors; Faculty action refresh verified; no live data changed');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});



