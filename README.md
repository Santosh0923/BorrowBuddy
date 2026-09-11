# BorrowBuddy

Existing React + Vite frontend and FastAPI + SQLAlchemy + PostgreSQL backend, upgraded in place.

## Run locally (Windows PowerShell)

From `C:\Santosh\Borrowbuddy`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd C:\Santosh\Borrowbuddy\frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8000. The current upgrade keeps both existing folders and the existing PostgreSQL database. For a separately hosted frontend set `VITE_API_URL` to the backend URL and configure its CORS origins. This local preview is not an internet deployment.

## Configuration and migration

`backend/.env` holds the existing DB settings and a random JWT signing secret. Do not commit or share this file. `backend/.env.example` documents the settings. `DATABASE_URL` can override the individual database variables. The secret is required; there is no insecure default. Existing passwords are unchanged. Old tokens signed with the former default secret require a fresh login.

To apply a future migration:

```powershell
.\.venv\Scripts\python.exe -B backend\upgrade_database.py
```

This saves a PostgreSQL custom-format backup under `backups/`, verifies it with `pg_restore --list`, applies checksum-tracked SQL migrations in a transaction, and checks all original values except documented legacy status mappings. `migrate.py` supports initialization of an empty database and standalone migrations. The default PostgreSQL tools path is `C:\Program Files\PostgreSQL\18\bin`; set `PG_DUMP` if needed. `--no-backup` is for disposable test databases only. Restore backups into a separate database with `pg_restore` and inspect them before any production recovery.

Migration preserves the old `Returned` request as `Completed`, with an explicit system audit note that historical actors, inspection results, and times are unknown. It does not invent request history or change original inventory quantities. Unmatched student emails or invalid stock cause migration to roll back for manual reconciliation.

## Roles and first setup

- Students create accounts, browse verified active resources, submit requests with quantity, purpose and return date, view their own history, and cancel their own Requested requests.
- Faculty own and submit resources, replenish their own stock, and manage requests for their resources through approval, pickup, handover, return inspection, and maintenance.
- Admins verify or reject listings, govern inventory, manage users and Faculty ownership, and oversee requests and exceptions. Routine request approval and physical handover belong to Faculty.

Sign in with your existing Admin account. In **Users**, manage Faculty accounts. In **Inventory**, assign an active Faculty owner to retained resources. In **Resource Verification**, review and verify listings before Student browsing. Faculty submissions and material listing edits enter **Pending Verification**. Rejected listings remain hidden from students and may be resubmitted by their owner.

Migrations `002_faculty_ownership.sql` and `003_owner_listing_identity.sql` convert current Staff accounts to Faculty, add listing verification metadata, and scope listing identity to the Faculty owner. Existing listings require verification; no existing listing is automatically trusted. Existing passwords, inventory quantities, request records, and historical audit actors are preserved. No test accounts or fixtures are inserted into the live database.

Each role has its own navigation and dashboard. Logout is available in the header and sidebar; it clears the browser session and replaces the current route with Sign in. Protected navigation and refresh recheck authentication. Audit history remains available within request details and through the Admin API, outside primary navigation.

The existing `backend/create_admin.py` remains available for authorized administrator bootstrap. It prompts interactively and never contains a default password.

## Workflow and inventory

Requested → Approved → Ready for Pickup → Collected → Returned Pending Inspection → Completed.

Requested may be rejected. Requests can be cancelled before collection; students can cancel only while Requested. Non-good inspection results enter Maintenance Required. Maintenance completion either restores repaired units or writes off unrecoverable units, with the custodian and notes recorded. Multi-unit requests are handled as a whole; partial returns/inspection are not supported.

Approval reserves stock. Collection does not deduct stock again, and return receipt does not restore availability. Good inspection and repaired maintenance restore stock once. Before-collection cancellation releases reserved stock. Retired records are retained, and open requests must be resolved before retirement. Changing a resource’s Faculty owner transfers all open requests together; an individual request cannot be assigned to a different resource owner.

All mutation routes share a transaction-scoped PostgreSQL advisory lock, acquired before reading state. This serializes mutations for the campus workload while ordinary reads remain concurrent, preventing duplicate approvals and lost stock updates. Database checks enforce valid statuses, roles, and nonnegative stock. Inventory adjustments protect outstanding reservations, loans, inspection, and maintenance quantities. `Other unavailable` exposes legacy/unallocated stock rather than silently adding it to availability. Administrators reconcile it with a recorded reason.

Request history and administrative audit events are append-only, enforced by database triggers. Request deletion is rejected; resource deletion retires it. User deactivation and role changes are blocked while assignments or loans need resolution. The API rechecks the active account and database role for every authenticated request.

## Verification

```powershell
.\.venv\Scripts\python.exe -B backend\tests\prepare_database.py
.\.venv\Scripts\python.exe -B backend\tests\test_integration.py
cd frontend
npm run lint
npm run build
```

Preparation backs up the existing database and restores into a randomly named `borrowbuddy_test_*` database. Integration tests refuse to target a database without that prefix. They start and stop a temporary API on port 8002, create fixtures only in the test database, and cover authentication, RBAC, complete lifecycle, concurrent approvals, cancellation, maintenance, inventory constraints, assignment transfer, retirement, user management, and immutable audit history. The test database remains isolated for inspection; `backend/.test-database` records its name. Sensitive backups, test configuration, environment files, dependencies, and build artifacts are ignored by Git.

API documentation: http://127.0.0.1:8000/docs. Health/schema check: http://127.0.0.1:8000/health.
