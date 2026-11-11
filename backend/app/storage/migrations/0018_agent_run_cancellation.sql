ALTER TABLE agent_runs ADD COLUMN cancel_requested_at TEXT;
ALTER TABLE agent_runs ADD COLUMN worker_id TEXT;
ALTER TABLE agent_runs ADD COLUMN lease_expires_at TEXT;
ALTER TABLE agent_runs ADD COLUMN token_budget INTEGER NOT NULL DEFAULT 0 CHECK (token_budget >= 0);
ALTER TABLE agent_runs ADD COLUMN token_reserved INTEGER NOT NULL DEFAULT 0 CHECK (token_reserved >= 0);
ALTER TABLE agent_runs ADD COLUMN token_actual INTEGER NOT NULL DEFAULT 0 CHECK (token_actual >= 0);
ALTER TABLE agent_runs ADD COLUMN heartbeat_at TEXT;
ALTER TABLE agent_runs ADD COLUMN phase TEXT NOT NULL DEFAULT 'executing'
    CHECK (phase IN ('accepted', 'executing', 'cancel_requested', 'completed', 'failed', 'cancelled', 'interrupted'));
UPDATE agent_runs SET phase = status
WHERE status IN ('completed', 'failed', 'cancelled', 'interrupted');
