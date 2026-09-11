-- The same resource type may be provided by different Faculty owners.
DROP INDEX resources_identity_normalized;
CREATE UNIQUE INDEX resources_owner_identity ON resources(custodian_id,lower(trim(name)),lower(trim(category)),lower(trim(location)));
