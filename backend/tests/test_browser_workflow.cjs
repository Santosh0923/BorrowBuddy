// Run with the isolated API on 8002 and Vite (proxying it) on 5174.
// NODE_PATH must contain Playwright; uses installed Edge in headless mode.
const { chromium, expect } = require('playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
assert.ok(fs.readFileSync(path.join(root, '.test-database'), 'utf8').trim().startsWith('borrowbuddy_test_'));
const accounts = JSON.parse(fs.readFileSync(path.join(root, '.test-browser.json'), 'utf8'));
const tokens = {};
const results = [];
const base = 'http://127.0.0.1:8002';
const site = 'http://127.0.0.1:5174';
async function api(route, who, method = 'GET', body, expected = 200) {
  const response = await fetch(base + route, { method, headers: {
    Authorization: 'Bearer ' + tokens[who], 'Content-Type': 'application/json',
  }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  assert.equal(response.status, expected, `${method} ${route}: ${JSON.stringify(data)}`);
  return data;
}
async function tokenFor(account) {
  const response = await fetch(base + '/auth/login', { method: 'POST',
    body: new URLSearchParams({ username: account.email, password: account.password }) });
  assert.equal(response.status, 200);
  return (await response.json()).access_token;
}
function record(message) { results.push(message); console.log('PASS:', message); }
(async () => {
  for (const role of ['student', 'faculty', 'admin']) tokens[role] = await tokenFor(accounts[role]);
  const resource = await api('/resources', 'faculty', 'POST', {
    name: 'Workflow continuity ' + Date.now(), category: 'Electronics', location: 'Test lab', quantity: 3,
  });
  assert.equal(resource.verification_status, 'Pending Verification');
  assert.ok(!(await api('/resources', 'student')).some(r => r.id === resource.id));
  await api(`/resources/${resource.id}/verify`, 'admin', 'POST', { decision: 'Verified' });
  const verified = await api(`/resources/${resource.id}`, 'student');
  assert.equal(verified.is_active, true);
  assert.ok(verified.verified_at && verified.verified_by === accounts.admin.id);
  const rejectedListing = await api('/resources', 'faculty', 'POST', { name: 'Rejected listing ' + Date.now(), category: 'Academic', location: 'Test lab', quantity: 1 });
  await api(`/resources/${rejectedListing.id}/verify`, 'admin', 'POST', { decision: 'Rejected', reason: 'Listing needs clarification.' });
  assert.ok(!(await api('/resources', 'student')).some(r => r.id === rejectedListing.id));
  record('Resource verification: pending/rejected hidden; verified active listing visible with reviewer/time');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    const resourceFailures = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('requestfailed', request => resourceFailures.push({ url: request.url(), error: request.failure()?.errorText }));
    page.on('console', message => {
      if (message.type() === 'error') errors.push({ text: message.text(), url: message.location().url });
    });
    async function login(role) {
      await page.goto(site + '/login');
      await page.getByLabel('University email', { exact: true }).fill(accounts[role].email);
      await page.getByLabel('Password', { exact: true }).fill(accounts[role].password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).last().click();
      await expect(page).toHaveURL(site + '/' + role + '/overview');
      await expect(page.getByRole('button', { name: 'Logout', exact: true })).toHaveCount(1);
      await expect(page.locator('.topbar').getByRole('button', { name: 'Logout' })).toHaveCount(0);
    }
    async function logout(role) {
      await page.getByRole('button', { name: 'Logout', exact: true }).click();
      await expect(page).toHaveURL(site + '/login');
      assert.equal(await page.evaluate(() => localStorage.getItem('borrowbuddy_token')), null);
      assert.equal(await page.evaluate(() => localStorage.getItem('borrowbuddy_user')), null);
      assert.equal(await page.evaluate(() => sessionStorage.getItem('borrowbuddy_user')), null);
      await page.goBack();
      await expect(page).toHaveURL(site + '/login');
      await expect(page.locator('.workspace')).toHaveCount(0);
      await page.reload();
      await expect(page.getByRole('heading', { name: 'Welcome back.' })).toBeVisible();
      await expect(page.locator('.workspace')).toHaveCount(0);
      record(role + ': one sidebar logout; token cleared; Back and refresh remain on Sign in');
    }
    await login('student');
    await page.getByRole('button', { name: 'Browse Resources', exact: true }).first().click();
    await page.getByLabel('Search resources', { exact: true }).fill(resource.name);
    await page.getByRole('button', { name: 'Request resource', exact: true }).click();
    await page.getByLabel('Quantity', { exact: true }).fill('2');
    const returnDate = new Date();
    returnDate.setDate(returnDate.getDate() + 7);
    await page.getByLabel('Required until / return date', { exact: true }).fill(returnDate.toISOString().slice(0, 10));
    await page.getByLabel('What will you use it for?', { exact: true }).fill('Verify continuous workflow and inventory.');
    const submitted = page.waitForResponse(r => r.url() === site + '/api/requests' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Submit request', exact: true }).click();
    const request = await (await submitted).json();
    assert.equal(request.status, 'Requested');
    assert.equal(request.custodian_id, accounts.faculty.id);
    assert.equal((await api(`/resources/${resource.id}`, 'faculty')).available_quantity, 3);
    let previousHistory = await api(`/requests/${request.id}/history`, 'student');
    await expect(page.locator('dialog[open]')).toHaveCount(0);
    await page.getByRole('button', { name: /My Requests/ }).first().click();
    await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
    await expect(page.locator('.workflow-steps [aria-current="step"]')).toHaveText('1Requested');
    await expect(page.locator('.timeline strong')).toHaveText('Request submitted');
    await expect(page.locator('.timeline')).not.toContainText('Review Student');
    await expect(page.locator('.timeline')).not.toContainText('Review Faculty');
    await expect(page.locator('.timeline')).not.toContainText('Verify continuous workflow and inventory.');
    await expect(page.getByRole('button', { name: 'Approve request', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    record('Student submitted Requested request assigned to resource Faculty owner');
    await logout('student');
    await login('faculty');
    await page.getByRole('button', { name: 'Issued Items / Returns', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Currently Issued', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Awaiting Return Inspection', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Maintenance Required', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Recently Completed Returns', exact: true })).toBeVisible();
    await page.getByLabel('Search returns', { exact: true }).fill(resource.name);
    await expect(page.getByRole('button', { name: 'Open request ' + request.id, exact: true })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'No matching returns', exact: true })).toHaveCount(4);
    await page.getByRole('button', { name: 'Overview', exact: true }).click();
    // Open from the Requested-only overview: approval used to close the detail and remove this row.
    await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
    const transitions = [
      ['Approve request', 'approve', 'Approved', 1],
      ['Mark ready for pickup', 'ready', 'Ready for Pickup', 2],
      ['Confirm physical handover', 'collect', 'Collected', 3],
      ['Receive physical return', 'return', 'Returned Pending Inspection', 4],
      ['Confirm return', 'inspect', 'Completed', 5],
    ];
    for (const [label, endpoint, status, index] of transitions) {
      await page.getByRole('button', { name: label, exact: true }).click();
      if (endpoint === 'inspect') await page.getByLabel('Inspection notes', { exact: true }).fill('Good condition; all units returned.');
      const saved = page.waitForResponse(r => r.url() === `${site}/api/requests/${request.id}/${endpoint}` && r.request().method() === 'POST');
      await page.getByRole('button', { name: 'Confirm & save', exact: true }).click();
      assert.equal((await saved).status(), 200);
      // No navigation, manual refresh, or reopening request details between actions.
      await expect(page.locator('.detail-top .badge')).toHaveText(status);
      await expect(page.locator('.workflow-steps li').nth(index)).toHaveAttribute('aria-current', 'step');
      await expect(page.locator('.timeline li')).toHaveCount(index + 1);
      await expect(page.locator('.timeline small').last()).toContainText('Review Faculty');
      await expect(page.locator('.timeline')).not.toContainText('user #');
      const currentHistory = await api(`/requests/${request.id}/history`, 'student');
      assert.equal(currentHistory.length, previousHistory.length + 1);
      assert.deepEqual(currentHistory.slice(0, -1), previousHistory);
      assert.ok(currentHistory.every(event => event.created_at && Number.isFinite(Date.parse(event.created_at))));
      assert.equal(new Set(currentHistory.map(event => event.id)).size, currentHistory.length);
      assert.equal(currentHistory.at(-1).action_by_user_id, accounts.faculty.id);
      previousHistory = currentHistory;
      const stock = await api(`/resources/${resource.id}`, 'faculty');
      assert.equal(stock.total_quantity, 3);
      assert.equal(stock.available_quantity, status === 'Completed' ? 3 : 1);
      record(`${endpoint}: ${status}; progress/history refreshed; stock ${stock.available_quantity}/3`);
      await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
      if (endpoint === 'approve' || endpoint === 'ready' || endpoint === 'collect') {
        await page.getByRole('button', { name: 'Issued Items / Returns', exact: true }).click();
        await page.getByLabel('Search returns', { exact: true }).fill(resource.name);
      }
      if (endpoint === 'approve' || endpoint === 'ready') {
        await expect(page.getByRole('button', { name: 'Open request ' + request.id, exact: true })).toHaveCount(0);
        await page.getByRole('button', { name: /Student Requests/ }).first().click();
      } else {
        const sectionName = { Collected: 'Currently Issued', 'Returned Pending Inspection': 'Awaiting Return Inspection', Completed: 'Recently Completed Returns' }[status];
        await expect(page.getByRole('region', { name: sectionName, exact: true }).getByRole('button', { name: 'Open request ' + request.id, exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Open request ' + request.id, exact: true })).toHaveCount(1);
        record(`Returns page: request immediately in ${sectionName}, without reload`);
      }
      await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
      if (status === 'Completed') await expect(page.locator('.detail-actions button')).toHaveCount(0);
    }
    const history = await api(`/requests/${request.id}/history`, 'student');
    assert.equal(history.length, 6);
    assert.equal(history[0].action_by_user_id, accounts.student.id);
    assert.ok(history.slice(1).every(event => event.action_by_user_id === accounts.faculty.id));
    await page.locator('.history-title').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(root, '.test-timeline-faculty.png') });
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await page.getByRole('button', { name: 'My Resources', exact: true }).first().click();
    await page.getByLabel('Search resources', { exact: true }).fill(resource.name);
    await expect(page.locator('.resource-stock')).toContainText('3 / 3 available');
    await logout('faculty');
    await login('student');
    // Exercise expansion with a long response fixture; never write synthetic
    // audit records to PostgreSQL just to test presentation.
    await page.route(`**/api/requests/${request.id}/history`, async route => {
      const extended = [...history, ...history.slice(1)].map((entry, index) => ({ ...entry, id: index + 1, action: 'INTERNAL_EVENT_CODE', remarks: 'Technical metadata user #999' }));
      extended.push({ ...history[0], id: 999, old_status: 'Requested', new_status: 'Requested', action: 'Ownership transfer', remarks: 'user #999' });
      await route.fulfill({ json: extended });
    });
    await page.getByRole('button', { name: 'Borrow History', exact: true }).first().click();
    await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
    await expect(page.locator('.timeline li')).toHaveCount(6);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('.timeline')).toBeVisible();
    assert.ok(await page.locator('dialog[open]').evaluate(element => element.scrollWidth <= element.clientWidth + 1));
    await page.locator('.history-title').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(root, '.test-timeline-student-mobile.png') });
    await page.reload();
    await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
    await expect(page.locator('.timeline li')).toHaveCount(6);
    await expect(page.getByRole('button', { name: 'View full history', exact: true })).toHaveAttribute('aria-expanded', 'false');
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.getByRole('button', { name: 'View full history', exact: true }).click();
    await expect(page.locator('.timeline li')).toHaveCount(11);
    await expect(page.locator('.timeline')).not.toContainText('Review Faculty');
    await expect(page.locator('.timeline')).not.toContainText('INTERNAL_EVENT_CODE');
    await expect(page.locator('.timeline')).not.toContainText('user #999');
    await page.getByRole('button', { name: 'Show less', exact: true }).click();
    await expect(page.locator('.timeline li')).toHaveCount(6);
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await page.unroute(`**/api/requests/${request.id}/history`);
    await logout('student');
    record('Student timeline is concise and hides actors/technical data even when full history is expanded');
    await login('admin');
    await page.getByRole('button', { name: /^Requests/ }).click();
    await page.getByRole('button', { name: 'Open request ' + request.id, exact: true }).click();
    await expect(page.locator('.detail-top .badge')).toHaveText('Completed');
    await expect(page.locator('.detail-actions button')).toHaveCount(0);
    await expect(page.locator('.timeline li')).toHaveCount(6);
    await expect(page.locator('.timeline small').last()).toContainText('Review Faculty');
    await expect(page.locator('.timeline')).not.toContainText('action_by');
    await expect(page.locator('.timeline')).not.toContainText('new_status');
    await page.locator('.history-title').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(root, '.test-timeline-admin.png') });
    await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    await logout('admin');
    for (const action of ['reject', 'cancel']) {
      const q = await api('/requests', 'student', 'POST', { resource_id: resource.id, quantity: 1, purpose: 'Regression check', return_date: returnDate.toISOString().slice(0, 10) });
      await api(`/requests/${q.id}/${action}`, action === 'reject' ? 'faculty' : 'student', action === 'cancel' ? 'PATCH' : 'POST', action === 'reject' ? { rejection_reason: 'Equipment reserved for examinations.' } : undefined);
      const events = await api(`/requests/${q.id}/history`, 'student');
      assert.equal(events.length, 2);
      assert.ok(events.every(event => event.created_at && Number.isFinite(Date.parse(event.created_at))));
      assert.equal(events[1].new_status, action === 'reject' ? 'Rejected' : 'Cancelled');
      if (action === 'reject') assert.equal(events[1].remarks, 'Equipment reserved for examinations.');
      assert.equal((await api(`/resources/${resource.id}`, 'faculty')).available_quantity, 3);
    }
    const fontUrl = url => /^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(url || '');
    assert.deepEqual(resourceFailures.filter(failure => !fontUrl(failure.url)), []);
    assert.deepEqual(errors.filter(error => typeof error === 'string' || !fontUrl(error.url)), []);
    if (resourceFailures.length) record('Optional external font loading failed; built-in fallback font used, no local app failures');
    record('Rejection/cancellation events, timestamps, reasons and unchanged stock verified');
    record('All six action actors and timestamps preserved; no application runtime errors');
    fs.writeFileSync(path.join(root, '.test-workflow-results.json'), JSON.stringify({ requestId: request.id, resourceId: resource.id, results }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
