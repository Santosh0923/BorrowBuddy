// Fresh restored isolated database must have zero Requested rows at start.
// --expect-bug reproduces the original blank-description verification reset.
const { chromium, expect } = require('playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const dbName = fs.readFileSync(path.join(root, '.test-database'), 'utf8').trim();
assert.ok(dbName.startsWith('borrowbuddy_test_'));
const accounts = JSON.parse(fs.readFileSync(path.join(root, '.test-browser.json'), 'utf8'));
const tokens = {};
const beforeFix = process.argv.includes('--expect-bug');
async function api(route, role, method = 'GET', body, status = 200) {
  const response = await fetch('http://127.0.0.1:8002' + route, { method, headers: { Authorization: 'Bearer ' + tokens[role], 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json(); assert.equal(response.status, status, JSON.stringify(data)); return data;
}
function databaseRequests() {
  const env = { ...process.env, DB_NAME: dbName }; delete env.DATABASE_URL;
  return JSON.parse(execFileSync(path.resolve(root, '../.venv/Scripts/python.exe'), ['-B', '-c', "import json;from database import engine;from sqlalchemy import text;c=engine.connect();print(json.dumps([dict(r) for r in c.execute(text('SELECT * FROM borrow_requests ORDER BY id')).mappings()],default=str));c.close()"], { cwd: root, env, encoding: 'utf8' }));
}
(async () => {
  for (const role of ['student', 'faculty', 'admin']) {
    const response = await fetch('http://127.0.0.1:8002/auth/login', { method: 'POST', body: new URLSearchParams({ username: accounts[role].email, password: accounts[role].password }) });
    assert.equal(response.status, 200); tokens[role] = (await response.json()).access_token;
  }
  assert.equal(databaseRequests().filter(r => r.status === 'Requested').length, 0);
  const suffix = Date.now();
  const resource = await api('/resources', 'faculty', 'POST', { name: 'Count regression ' + suffix, category: 'Academic', location: 'Test lab', quantity: 5 });
  await api(`/resources/${resource.id}/verify`, 'admin', 'POST', { decision: 'Verified' });
  const date = new Date(); date.setDate(date.getDate() + 7);
  const create = () => api('/requests', 'student', 'POST', { resource_id: resource.id, quantity: 1, purpose: 'Pending-count regression', return_date: date.toISOString().slice(0, 10) });
  const requests = [];
  for (let i = 0; i < 3; i++) requests.push(await create());
  // Admin cannot reject a borrowing request; retain the existing Faculty RBAC.
  await api(`/requests/${requests[0].id}/reject`, 'admin', 'POST', { rejection_reason: 'Not allowed' }, 403);
  for (const request of requests) await api(`/requests/${request.id}/reject`, 'faculty', 'POST', { rejection_reason: 'Not needed for this course.' });
  const before = databaseRequests();
  assert.ok(requests.every(r => before.find(row => row.id === r.id).status === 'Rejected'));
  assert.equal(before.filter(r => r.status === 'Requested').length, 0);
  assert.equal((await api('/requests', 'admin')).filter(r => r.status === 'Requested').length, 0);
  assert.equal((await api('/dashboard/admin', 'admin')).pending_requests, 0);
  const exception = await api('/resources', 'faculty', 'POST', { name: 'Exception count regression ' + suffix, category: 'Electronics', location: 'Test lab', quantity: 1 });
  assert.equal(exception.description, null);
  await api(`/resources/${exception.id}/verify`, 'admin', 'POST', { decision: 'Rejected', reason: 'Listing needs correction.' });
  await api(`/resources/${exception.id}`, 'admin', 'PATCH', { status: 'Maintenance' });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:5174/login');
    await page.getByLabel('University email', { exact: true }).fill(accounts.admin.email);
    await page.getByLabel('Password', { exact: true }).fill(accounts.admin.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).last().click();
    await page.getByRole('button', { name: 'Exceptions / Maintenance', exact: true }).click();
    await page.getByLabel('Search resources', { exact: true }).fill(exception.name);
    await page.getByRole('button', { name: 'Manage resource', exact: true }).click();
    const saved = page.waitForResponse(r => r.url().endsWith(`/api/resources/${exception.id}`) && r.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Confirm & save', exact: true }).click();
    assert.equal((await saved).status(), 200);
    await expect(page.locator('dialog[open]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Overview', exact: true }).click();
    assert.deepEqual(databaseRequests(), before);
    const after = await api(`/resources/${exception.id}`, 'admin');
    assert.equal(after.verification_status, beforeFix ? 'Pending Verification' : 'Rejected');
    assert.equal((await api('/dashboard/admin', 'admin')).pending_requests, 0);
    assert.equal((await api('/requests', 'admin')).filter(r => r.status === 'Requested').length, 0);
    console.log('BorrowRequest IDs rejected:', requests.map(r => r.id).join(', '));
    console.log('No-op resource save: all BorrowRequest columns unchanged; DB/API pending=0; listing status=' + after.verification_status);
    if (beforeFix) { console.log('REPRODUCED: blank description save resets Rejected listing to Pending Verification'); return; }
    assert.equal(after.verification_reason, 'Listing needs correction.');
    assert.equal(after.description, null);
    await expect(page.locator('.stat').filter({ hasText: 'Pending requests' }).locator('strong')).toHaveText('0');
    const newRequests = [await create(), await create()];
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.locator('.stat').filter({ hasText: 'Pending requests' }).locator('strong')).toHaveText('2');
    assert.equal(databaseRequests().filter(r => r.status === 'Requested').length, 2);
    assert.equal((await api('/requests', 'admin')).filter(r => r.status === 'Requested').length, 2);
    assert.equal((await api('/dashboard/admin', 'admin')).pending_requests, 2);
    console.log('New Requested IDs:', newRequests.map(r => r.id).join(', '), 'DB/API/Overview all show 2');
    await page.getByRole('button', { name: 'Exceptions / Maintenance', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Resource exceptions', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Request exceptions', exact: true })).toBeVisible();
    await page.getByLabel('Search resources', { exact: true }).fill(exception.name);
    await expect(page.getByLabel('Search requests', { exact: true })).toHaveValue('');
    await expect(page.getByRole('button', { name: 'Open request ' + newRequests[0].id, exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'View all requests', exact: true }).click();
    await page.getByLabel('Filter request status', { exact: true }).selectOption('Requested');
    await expect(page.locator('tbody tr')).toHaveCount(2);
    console.log('PASS: separate exception searches; Requested records excluded intentionally; View all requests shows both');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
