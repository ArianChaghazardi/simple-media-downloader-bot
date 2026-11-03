-- Initial Schema for Simple Media Downloader Bot
-- Supports: Instagram, YouTube, Twitter/X, TikTok, Pinterest, Threads, Reddit

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    first_name TEXT,
    username TEXT,
    is_banned INTEGER DEFAULT 0,
    daily_downloads_used INTEGER DEFAULT 0,
    last_download_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_groups (
    chat_id BIGINT PRIMARY KEY,
    title TEXT,
    is_active INTEGER DEFAULT 1,
    daily_downloads_used INTEGER DEFAULT 0,
    last_download_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS downloads_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    platform TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    status TEXT DEFAULT 'pending',
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    worker_id TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id BIGINT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cooldowns (
    cooldown_key TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_states (
    user_id BIGINT PRIMARY KEY,
    state TEXT NOT NULL,
    context_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_downloads_stats_platform ON downloads_stats(platform);
CREATE INDEX IF NOT EXISTS idx_downloads_stats_created ON downloads_stats(created_at);
