ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE resources ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE resources ADD COLUMN IF NOT EXISTS custodian_id integer REFERENCES users(id);
ALTER TABLE resources ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE resources ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS student_id integer REFERENCES users(id);
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS approved_by integer REFERENCES users(id);
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS rejection_reason text;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS custodian_id integer REFERENCES users(id);
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS ready_at timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS collected_at timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS returned_at timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS inspection_condition varchar(50);
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS inspection_notes text;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS inspected_by integer REFERENCES users(id);
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS inspection_date timestamptz;
ALTER TABLE borrow_requests ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- Match existing identities only; never invent accounts or historical actors.
UPDATE borrow_requests b SET student_id = u.id FROM users u
WHERE b.student_id IS NULL AND lower(trim(b.student_email)) = lower(trim(u.email));
ALTER TABLE borrow_requests ALTER COLUMN student_id SET NOT NULL;

CREATE TABLE IF NOT EXISTS audit_events (
 id serial PRIMARY KEY, entity_type varchar(50) NOT NULL, entity_id integer,
 action varchar(200) NOT NULL, actor_id integer REFERENCES users(id),
 actor_name varchar(100) NOT NULL, actor_role varchar(20) NOT NULL,
 details text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO audit_events(entity_type, entity_id, action, actor_name, actor_role, details)
SELECT 'request', id, 'Legacy status migration', 'Database migration', 'system',
 '{"old_status":"Returned","new_status":"Completed","note":"Legacy returned record. Historical return time, inspector and actor are unknown; no inspection is asserted."}'
FROM borrow_requests WHERE status = 'Returned';
UPDATE borrow_requests SET status = 'Completed' WHERE status = 'Returned';
UPDATE borrow_requests SET status = 'Returned Pending Inspection' WHERE status = 'Returned - Pending Inspection';
UPDATE request_history SET old_status = 'Returned Pending Inspection' WHERE old_status = 'Returned - Pending Inspection';
UPDATE request_history SET new_status = 'Returned Pending Inspection' WHERE new_status = 'Returned - Pending Inspection';

ALTER TABLE users ADD CONSTRAINT users_role_valid CHECK (role IN ('student','faculty','staff','admin'));
ALTER TABLE resources ADD CONSTRAINT resource_quantities_valid CHECK (total_quantity >= 0 AND available_quantity >= 0 AND available_quantity <= total_quantity);
ALTER TABLE resources ADD CONSTRAINT resource_status_valid CHECK (status IN ('Available','Out of Stock','Maintenance','Retired'));
ALTER TABLE borrow_requests ADD CONSTRAINT request_quantity_positive CHECK (quantity > 0);
ALTER TABLE borrow_requests ADD CONSTRAINT request_status_valid CHECK (status IN ('Requested','Approved','Ready for Pickup','Collected','Returned Pending Inspection','Completed','Rejected','Cancelled','Maintenance Required'));
CREATE UNIQUE INDEX users_email_normalized ON users(lower(trim(email)));
CREATE UNIQUE INDEX resources_identity_normalized ON resources(lower(trim(name)),lower(trim(category)),lower(trim(location)));
CREATE INDEX requests_custodian_status ON borrow_requests(custodian_id,status);
CREATE INDEX requests_student_status ON borrow_requests(student_id,status);
CREATE INDEX request_history_request ON request_history(request_id,created_at);

-- Application audit records are append-only, including for privileged API users.
CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit records are append-only'; END; $$;
CREATE TRIGGER request_history_immutable BEFORE UPDATE OR DELETE ON request_history FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
