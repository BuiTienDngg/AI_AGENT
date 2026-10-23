CREATE TABLE IF NOT EXISTS admin_auth (id INTEGER PRIMARY KEY CHECK(id=1), password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS secure_values (id TEXT PRIMARY KEY, ciphertext TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS capacity_settings (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provider_configs (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, model TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
 priority INTEGER NOT NULL DEFAULT 100, status TEXT NOT NULL DEFAULT 'UNKNOWN', checked TEXT, error TEXT NOT NULL DEFAULT '',
 max_job_tokens INTEGER NOT NULL DEFAULT 1000000, secret_ref TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_assignments (
 job_id TEXT PRIMARY KEY, provider_id TEXT, kind TEXT, state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
 attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0, started TEXT, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS assignments_state ON job_assignments(state,next_retry);
CREATE TABLE IF NOT EXISTS workflow_usage (
 job_id TEXT PRIMARY KEY, provider_id TEXT, model TEXT, result TEXT, input_tokens INTEGER, cached_input_tokens INTEGER,
 output_tokens INTEGER, total_tokens INTEGER, duration_seconds REAL, delta_5h REAL, delta_week REAL, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS usage_provider ON workflow_usage(provider_id,result);
CREATE TABLE IF NOT EXISTS account_audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, timestamp TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS profile_samples_date ON codex_profile_samples(profile_id,checked);
CREATE VIEW IF NOT EXISTS codex_accounts AS SELECT * FROM codex_profiles;
CREATE VIEW IF NOT EXISTS quota_snapshots AS SELECT * FROM codex_profile_samples;
CREATE TABLE IF NOT EXISTS job_request_keys (key TEXT PRIMARY KEY, game_id TEXT NOT NULL, job_id TEXT NOT NULL);
ALTER TABLE codex_profiles ADD COLUMN model TEXT NOT NULL DEFAULT '';
ALTER TABLE codex_profiles ADD COLUMN source TEXT NOT NULL DEFAULT 'official';
ALTER TABLE job_assignments ADD COLUMN providers_used TEXT NOT NULL DEFAULT '[]';
