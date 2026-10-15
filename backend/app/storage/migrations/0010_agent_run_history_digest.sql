ALTER TABLE agent_runs
ADD COLUMN history_sha256 TEXT NOT NULL
DEFAULT '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'
CHECK (length(history_sha256) = 64);
