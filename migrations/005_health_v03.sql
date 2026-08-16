-- FamilyStream v0.3 adaptive source health state.
CREATE TABLE IF NOT EXISTS playback_source_state (
    stream_id TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    ewma_latency_ms REAL,
    last_http_status INTEGER,
    last_result TEXT,
    last_error_code TEXT,
    last_success TEXT,
    last_failure TEXT,
    quarantine_until TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(stream_id, item_kind)
);

CREATE INDEX IF NOT EXISTS idx_playback_source_state_health
    ON playback_source_state(item_kind, consecutive_failures, quarantine_until, updated_at);
