ALTER TABLE agent_runs ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX idx_agent_runs_user ON agent_runs(user_id, created_at DESC);
