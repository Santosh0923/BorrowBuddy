-- Preserve historical audit actors; only current accounts change role.
INSERT INTO audit_events(entity_type, entity_id, action, actor_name, actor_role, details)
SELECT 'user', id, 'Role model migration', 'Database migration', 'system',
 '{"old_role":"staff","new_role":"faculty"}' FROM users WHERE role='staff';
ALTER TABLE users DROP CONSTRAINT users_role_valid;
UPDATE users SET role='faculty' WHERE role='staff';
ALTER TABLE users ADD CONSTRAINT users_role_valid CHECK (role IN ('student','faculty','admin'));

ALTER TABLE resources ADD COLUMN IF NOT EXISTS verification_status varchar(30) NOT NULL DEFAULT 'Pending Verification';
ALTER TABLE resources ADD COLUMN IF NOT EXISTS verification_reason text;
ALTER TABLE resources ADD COLUMN IF NOT EXISTS verified_by integer REFERENCES users(id);
ALTER TABLE resources ADD COLUMN IF NOT EXISTS verified_at timestamptz;
ALTER TABLE resources ADD CONSTRAINT resource_verification_valid CHECK (verification_status IN ('Pending Verification','Verified','Rejected'));
CREATE INDEX resources_verification ON resources(verification_status,is_active);
-- No evidence of prior listing verification exists. Preserve quantities and
-- request history, but require review before any further student borrowing.
INSERT INTO audit_events(entity_type, entity_id, action, actor_name, actor_role, details)
SELECT 'resource', id, 'Listing requires verification', 'Database migration', 'system',
 '{"verification_status":"Pending Verification","reason":"Existing listing retained; verification required under the faculty ownership model."}' FROM resources;
