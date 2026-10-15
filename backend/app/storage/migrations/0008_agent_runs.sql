CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    question_sha256 TEXT NOT NULL CHECK (length(question_sha256) = 64),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')),
    result_status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    model_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (model_input_tokens >= 0),
    model_output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (model_output_tokens >= 0),
    total_observed_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_observed_tokens >= 0),
    tool_calls INTEGER NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
    model_steps INTEGER NOT NULL DEFAULT 0 CHECK (model_steps >= 0),
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    trace_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_updated ON agent_runs(updated_at DESC);
