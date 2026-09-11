# BorrowBuddy continuation review — 11 September 2026

READY FOR GITHUB PRE-CHECK: YES

## Resumed point

Resumed at Faculty login for the already-submitted browser request BB-0017, for resource #21, Browser review camera. The prior temporary services had stopped; restarted them against the retained isolated database `borrowbuddy_test_9d9c350828`. Did not recreate the implementation or the original request.

## Files changed in this continuation

- `frontend/src/views.jsx`: changed the remaining request-detail Custodian label to Faculty owner, plus a fallback label.
- `frontend/src/forms.jsx`: removed the obsolete Staff choice from the Admin role editor. The three choices are Student, Faculty, Admin.
- `backend/tests/test_integration.py`: added an explicit Student verification attempt expecting 403 to the existing verification test.
- `README.md`: updated role, listing verification, migration, session, and ownership-transfer documentation to match the implementation.
- `ROLE_FLOW_REVIEW.md`: this verification report.

No new features or visual redesign were added. Generated frontend build artifacts and ignored test logs were refreshed.

## Live database

Before migration: `borrowbuddy_db` had migration 001, 5 users (including one Staff), 2 resources, 1 request, and no historical request-history rows. Resource stock was 0/0 and 5/5 available/total.

Created and validated PostgreSQL backup `backups/20260910T235709645588Z.dump` before applying only:

- `002_faculty_ownership.sql`: current Staff becomes Faculty; listing verification status, reason, reviewer and timestamp columns; three-role constraint and verification constraint/index; explicit migration audit events.
- `003_owner_listing_identity.sql`: listing identity uniqueness is scoped to Faculty ownership.

The migration runner verified every original row ID and column value, except the documented Staff-to-Faculty mapping. All 5 users, both resources, the existing request, passwords and inventory quantities were preserved. No test data was inserted into the live database. Both retained listings remain Pending Verification with no Faculty owner; an Admin must assign ownership and verify them before Student borrowing.

The stale local API worker was restarted. Live `/health` confirms PostgreSQL connectivity and schema 003; the live API now exposes verification and replenishment endpoints. The main frontend on port 5173 loads Sign in successfully.

## End-to-end browser results

| Check | Result |
|---|---|
| Student login and dedicated portal | PASS — Student navigation only; no Faculty/Admin controls |
| Verified active resource browsing, quantity/purpose/date submission | PASS — existing BB-0017 retained; new requests BB-0018 and BB-0019 submitted through the browser |
| Student My Requests | PASS — Requested requests appear with correct quantity/date and Faculty owner |
| Correct Faculty queue | PASS — BB-0017 appears for Review Faculty with student, resource, quantity, purpose and return date |
| Approval, Ready for Pickup, Collected | PASS — same BB-0017 progresses through each state |
| Return receipt and Good inspection | PASS — Returned Pending Inspection then Completed; Student sees completed borrowing history |
| Rejection | PASS — BB-0018 rejected by Faculty; reason appears in Student history |
| Student cancellation | PASS — BB-0019 cancelled while Requested; Student actor and history retained |
| Admin governance | PASS — pending listings visible; listing #15 rejected with stored reason; #17 verified; inventory, requests and users inspected |
| Admin role choices | PASS — exactly Student, Faculty, Admin |
| Logout for Student, Faculty and Admin | PASS — Back and refresh stay on Sign in; protected content is absent |
| Browser runtime | PASS — no captured console warnings/errors during role checks or main-site Sign in check |

## Inventory and history evidence

Resource #21: total 2, available 2 before approval; available 1 after approval; still 1 after collection; available 2 after Good inspection. Rejection of quantity 2 and cancellation of quantity 1 left stock at total 2 / available 2.

Database readback confirms BB-0017 Completed, BB-0018 Rejected, and BB-0019 Cancelled. BB-0017 has all six transitions: Requested by Student #16; Approved, Ready for Pickup, Collected, Returned Pending Inspection, Completed by Faculty #14. Rejection and cancellation histories preserve their actors. Browser request details also display the actors, remarks and timestamps.

## Automated tests

- Full backend integration suite: **20 passed, 0 failed** (19.580 seconds), using the isolated database.
- After adding the explicit Student verification denial assertion: focused verification/RBAC test **passed** (10.548 seconds).
- Frontend ESLint: **passed**.
- Frontend production build: **passed** (23 modules).

Coverage includes public registration forcing Student even when a role is supplied; missing/invalid authentication returning 401; Student resource creation and request approval returning 403; Student and Faculty verification returning 403; unrelated Faculty requests/history inaccessible; Admin routes protected; verified/active access; full lifecycle; concurrent approvals; inventory invariants; maintenance; ownership transfer; retirement; and immutable history.

## Remaining known issues / scope limits

- No blocking defect found in the tested core role flow or logout behavior.
- Live retained listings need real Admin ownership assignment and verification before they become borrowable. They were intentionally not automatically trusted.
- Multi-unit requests still return and inspect as a whole; partial returns remain unsupported by the existing design.
- The legacy completed request has no historical action records; migration does not fabricate missing actors or dates.
- Browser flows used isolated accounts and fixtures; real user passwords were not changed or used for test mutations.
- This is a local review, not a deployment or comprehensive security/load audit. No GitHub push, Docker or cloud deployment was performed.

Local website: http://127.0.0.1:5173
