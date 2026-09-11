// Requires isolated API :8002, Vite :5174, and Playwright on NODE_PATH.
const { chromium, expect } = require('playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
assert.ok(fs.readFileSync(path.join(root, '.test-database'), 'utf8').trim().startsWith('borrowbuddy_test_'));
const accounts = JSON.parse(fs.readFileSync(path.join(root, '.test-browser.json'), 'utf8'));
const tokens = {};
async function api(route, role, method = 'GET', body) {
  const response = await fetch('http://127.0.0.1:8002' + route, { method, headers: {
    Authorization: 'Bearer ' + tokens[role], 'Content-Type': 'application/json',
  }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  assert.equal(response.status, 200, `${route}: ${JSON.stringify(data)}`);
  return data;
}
(async () => {
  for (const role of ['student', 'faculty', 'admin']) {
    const response = await fetch('http://127.0.0.1:8002/auth/login', { method: 'POST', body: new URLSearchParams({ username: accounts[role].email, password: accounts[role].password }) });
    assert.equal(response.status, 200); tokens[role] = (await response.json()).access_token;
  }
  const name = 'List usability ' + Date.now();
  const resource = await api('/resources', 'faculty', 'POST', { name, category: 'Electronics', location: 'Test lab', quantity: 30 });
  await api(`/resources/${resource.id}/verify`, 'admin', 'POST', { decision: 'Verified' });
  const states = ['Requested', 'Requested', 'Requested', 'Approved', 'Approved', 'Ready for Pickup', 'Ready for Pickup', 'Collected', 'Collected', 'Returned Pending Inspection', 'Maintenance Required', 'Completed', 'Rejected', 'Cancelled', 'Collected', 'Collected', 'Collected', 'Returned Pending Inspection', 'Maintenance Required', 'Completed'];
  const records = [];
  const date = new Date(); date.setDate(date.getDate() + 7);
  for (const state of states) {
    const request = await api('/requests', 'student', 'POST', { resource_id: resource.id, quantity: 1, purpose: 'List usability verification', return_date: date.toISOString().slice(0, 10) });
    const actions = { Requested: [], Approved: ['approve'], 'Ready for Pickup': ['approve', 'ready'], Collected: ['approve', 'ready', 'collect'], 'Returned Pending Inspection': ['approve', 'ready', 'collect', 'return'], 'Maintenance Required': ['approve', 'ready', 'collect', 'return', 'inspect'], Completed: ['approve', 'ready', 'collect', 'return', 'inspect'], Rejected: ['reject'], Cancelled: ['cancel'] }[state];
    for (const action of actions) await api(`/requests/${request.id}/${action}`, action === 'cancel' ? 'student' : 'faculty', action === 'cancel' ? 'PATCH' : 'POST', action === 'inspect' ? { condition: state === 'Completed' ? 'Good' : 'Minor Damage', notes: 'Test condition' } : action === 'reject' ? { rejection_reason: 'Test rejection' } : undefined);
    records.push({ id: request.id, state });
  }
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5174/login');
    await page.getByLabel('University email', { exact: true }).fill(accounts.faculty.email);
    await page.getByLabel('Password', { exact: true }).fill(accounts.faculty.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).last().click();
    await page.getByRole('button', { name: /Student Requests/ }).first().click();
    const search = page.getByLabel('Search requests', { exact: true });
    const filter = page.getByLabel('Filter request status', { exact: true });
    await search.fill(name);
    await expect(page.locator('tbody tr')).toHaveCount(20);
    await expect(page.locator('.count-label')).toContainText('Showing 20 of');
    await page.locator('tbody tr').last().scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => window.scrollY > 0));
    console.log('PASS: 20 sample requests; normal page scrolling and result count');
    for (const status of ['Requested', 'Approved', 'Ready for Pickup', 'Rejected', 'Cancelled']) {
      await filter.selectOption(status);
      await expect(page.locator('tbody tr')).toHaveCount(states.filter(s => s === status).length);
    }
    await filter.selectOption('Approved');
    await search.fill(accounts.student.email);
    const matching = (await api('/requests', 'faculty')).filter(r => r.status === 'Approved' && r.student_email === accounts.student.email);
    await expect(page.locator('tbody tr')).toHaveCount(matching.length);
    await filter.selectOption('');
    await search.fill('Review Student'); await expect(page.locator('tbody tr')).not.toHaveCount(0);
    await search.fill('Ready for Pickup'); await expect(page.locator('tbody tr')).not.toHaveCount(0);
    const chosen = records[0];
    await filter.selectOption('Requested');
    await search.fill(`BB-${String(chosen.id).padStart(4, '0')}`);
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await page.getByRole('button', { name: 'Open request ' + chosen.id, exact: true }).click();
    await page.getByRole('button', { name: 'Approve request', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm & save', exact: true }).click();
    await expect(page.locator('.detail-top .badge')).toHaveText('Approved');
    assert.equal((await api(`/requests/${chosen.id}`, 'faculty')).status, 'Approved');
    assert.equal((await api(`/requests/${records[1].id}`, 'faculty')).status, 'Requested');
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await expect(page.locator('tbody tr')).toHaveCount(0);
    console.log('PASS: name/email/resource/ID/status search, combined filters, correct filtered-row approval');
    await page.getByRole('button', { name: 'Issued Items / Returns', exact: true }).click();
    const returnsSearch = page.getByLabel('Search returns', { exact: true });
    const returnsFilter = page.getByLabel('Filter return status', { exact: true });
    await returnsSearch.fill(name);
    await expect(page.locator('tbody tr')).toHaveCount(11);
    await expect(page.locator('.toolbar .count-label')).toContainText('Showing 11 of');
    await page.locator('tbody tr').last().scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => window.scrollY > 0));
    console.log('PASS: 11 return-stage records; normal page scrolling and result count');
    for (const status of ['Collected', 'Returned Pending Inspection', 'Maintenance Required', 'Completed']) {
      await returnsFilter.selectOption(status);
      await expect(page.locator('tbody tr')).toHaveCount(states.filter(s => s === status).length);
    }
    await returnsFilter.selectOption('Collected');
    await returnsSearch.fill(accounts.student.email);
    await expect(page.locator('tbody tr')).not.toHaveCount(0);
    const issued = records.find(r => r.state === 'Collected');
    await returnsSearch.fill(`BB-${String(issued.id).padStart(4, '0')}`);
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await page.getByRole('button', { name: 'Open request ' + issued.id, exact: true }).click();
    await page.getByRole('button', { name: 'Receive physical return', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm & save', exact: true }).click();
    await expect(page.locator('.detail-top .badge')).toHaveText('Returned Pending Inspection');
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await expect(page.locator('tbody tr')).toHaveCount(0);
    await returnsFilter.selectOption('Returned Pending Inspection');
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await returnsSearch.fill('Completed'); await returnsFilter.selectOption('Completed');
    await expect(page.locator('tbody tr')).not.toHaveCount(0);
    assert.deepEqual(errors, []);
    console.log('PASS: returns search/status combinations and correct-row return action; no runtime errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
