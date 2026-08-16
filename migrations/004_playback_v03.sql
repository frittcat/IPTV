-- FamilyStream v0.3 playback resolver and technical capability cache.
-- Kept separate from provider credentials and URLs so diagnostics can be exposed safely.
CREATE TABLE IF NOT EXISTS stream_technical_profiles (
    stream_id TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    protocol TEXT,
    container TEXT,
    video_codec TEXT,
    audio_codec TEXT,
    width INTEGER,
    height INTEGER,
    bitrate BIGINT,
    fps REAL,
    hdr TEXT,
    audio_channels REAL,
    probe_status TEXT DEFAULT 'new',
    probed_at TEXT,
    PRIMARY KEY(stream_id, item_kind)
);

CREATE INDEX IF NOT EXISTS idx_stream_technical_kind_codec
    ON stream_technical_profiles(item_kind, video_codec, height);

CREATE INDEX IF NOT EXISTS idx_stream_technical_probe
    ON stream_technical_profiles(probe_status, probed_at);
