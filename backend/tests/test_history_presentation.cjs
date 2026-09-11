const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const modulePath = pathToFileURL(path.resolve(__dirname, '../../frontend/src/requestHistory.js')).href;
const date = '2026-09-11T12:00:00Z';
const records = [
  { id: 91, old_status: null, new_status: 'Requested', action: 'INTERNAL_REQUEST_CREATED', action_by_user_id: 72, action_by_name: 'A Student', created_at: date, remarks: 'Repeated purpose' },
  { id: 92, old_status: 'Requested', new_status: 'Requested', action: 'Faculty ownership transferred', action_by_user_id: 73, action_by_name: 'An Admin', created_at: date, remarks: 'Faculty owner changed to user #456' },
  { id: 93, old_status: 'Requested', new_status: 'Rejected', action: 'INTERNAL_REJECT', action_by_user_id: 74, action_by_name: 'A Faculty member', created_at: date, remarks: 'Equipment is reserved for an exam.' },
  { id: 94, old_status: 'Rejected', new_status: 'INTERNAL_UNKNOWN', action: 'DATABASE_EVENT', created_at: date },
];
test('Student receives only meaningful lifecycle events, times and concise notes', async () => {
  const { presentHistory } = await import(modulePath);
  const events = presentHistory(records, 'student');
  assert.equal(events.length, 2);
  assert.deepEqual(events[0], { title: 'Request submitted', note: 'Awaiting Faculty review.', date });
  assert.deepEqual(events[1], { title: 'Request rejected', note: '', date });
  assert.doesNotMatch(JSON.stringify(events), /INTERNAL|user #|action_by|old_status|new_status|Repeated purpose|reserved|Student|Faculty member/);
});
test('Faculty and Admin see an actor once and relevant reason without raw audit fields', async () => {
  const { presentHistory } = await import(modulePath);
  for (const role of ['faculty', 'admin']) {
    const events = presentHistory(records, role);
    assert.equal(events[1].actor, 'A Faculty member');
    assert.equal(events[1].reason, 'Equipment is reserved for an exam.');
    assert.equal(events[0].reason, undefined);
    assert.doesNotMatch(JSON.stringify(events), /INTERNAL|user #|action_by|old_status|new_status|Repeated purpose/);
  }
});
test('Long history keeps submission and latest five events; short history stays complete', async () => {
  const { compactHistory } = await import(modulePath);
  const events = Array.from({ length: 12 }, (_, index) => ({ title: `Event ${index}` }));
  assert.deepEqual(compactHistory(events), [events[0], ...events.slice(-5)]);
  assert.equal(compactHistory(events.slice(0, 6)).length, 6);
});
