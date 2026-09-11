# Timeline regression continuation — 11 September 2026

READY FOR GITHUB PRE-CHECK: YES

## Resumed point

Resumed the pending browser run after Student submission. The implementation and isolated API/Vite services were intact. That run completed its functional checks but failed its final console assertion on network-resource failures. The application references optional Google Fonts. The test now captures failure URLs and distinguishes confirmed external font failures from local application failures; the final run had no application runtime errors.

## Results

| Area | Result |
|---|---|
| Student timeline | PASS: readable lifecycle titles, date/time and short notes; no actor names, raw action codes, assignment IDs or technical remarks in the timeline |
| Faculty/Admin timeline | PASS: readable lifecycle titles with actor/time; relevant rejection/cancellation reasons supported by role-presentation tests; raw audit fields omitted |
| Long history | PASS: six events initially, expanded sanitized history, collapse to six; no duplicate entries introduced by expansion; compact state restored after refresh |
| Narrow layout | PASS at 390px after fixing progress labels that previously broke mid-word; no horizontal dialog overflow |
| Full lifecycle | PASS: request BB-0085, Requested → Approved → Ready for Pickup → Collected → Returned Pending Inspection → Completed |
| History integrity | PASS: exactly one event per transition; earlier records/timestamps unchanged; six unique events with correct Student/Faculty actors |
| Returns sections | PASS: collection, inspection and completion appear immediately in the correct section without reload; Completed is read-only |
| Search/filter | PASS with 20 sample requests, including 11 return-stage records; combined filters, counts, scrolling and correct-row actions |
| Inventory | PASS: quantity 2 requested from total 3; availability 3 on submission, 1 after approval through inspection receipt, 3 after Good completion; no double deductions/restoration |
| Maintenance | PASS in integration suite: damaged returns remain unavailable; repaired maintenance restores stock; repeated/invalid transitions rejected |
| Rejection/cancellation | PASS: two-event histories with valid timestamps, stored rejection reason and unchanged availability |
| Logout | PASS for Student, Faculty and Admin: one sidebar control, cleared browser session, Sign in redirect, Back and refresh remain logged out |
| Resource verification | PASS: Faculty submission pending, Admin verification preserves active state and reviewer/time, Student visibility after verification; pending/rejected listings hidden |

## Tests

- Full browser workflow/timeline regression: passed.
- Browser list regression with 20 records: passed.
- History-presentation unit tests: 3 passed, 0 failed.
- Backend integration suite: 20 passed, 0 failed, 13.263 seconds.
- Frontend lint and final production build: passed.
- Desktop Faculty/Admin and narrow Student screenshots inspected. Screenshot/test artifacts are under ignored `backend/.test-*` paths.

## Files changed during this continuation

- `frontend/src/App.css`: only the observed narrow-layout defect; progress steps use three columns below 650px so words remain readable.
- `backend/tests/test_browser_workflow.cjs`: extended assertions for role-specific timeline content, history timestamps/uniqueness, expansion, refresh, narrow layout, resource verification, rejection/cancellation, screenshots and network-failure attribution.
- `TIMELINE_REGRESSION_REVIEW.md`: this report.

No backend workflow, audit, inventory or schema changes. No live database mutations for tests. All test fixtures used the retained isolated database.

## Remaining known issues

No blocking core-flow defect found. Optional external fonts can fail when the network is unavailable; built-in fallback fonts remain usable. Existing live listings still require real Faculty ownership and Admin verification. Historical missing audit records were not fabricated. Partial multi-unit returns remain outside the existing design.

No GitHub push, Docker, or cloud deployment performed.
