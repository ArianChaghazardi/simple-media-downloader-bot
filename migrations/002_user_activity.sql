-- Migration 002: Daily User Activity Tracking for DAU, WAU, and MAU Metrics

CREATE TABLE IF NOT EXISTS user_activity_daily (
    user_id BIGINT NOT NULL,
    activity_date TEXT NOT NULL,
    last_action_at TEXT NOT NULL,
    PRIMARY KEY (user_id, activity_date)
);

CREATE INDEX IF NOT EXISTS idx_activity_date ON user_activity_daily(activity_date);

-- Backfill activity history from existing downloads_stats and jobs
INSERT OR IGNORE INTO user_activity_daily (user_id, activity_date, last_action_at)
SELECT user_id, substr(created_at, 1, 10), created_at
FROM downloads_stats
WHERE user_id IS NOT NULL AND user_id > 0;

INSERT OR IGNORE INTO user_activity_daily (user_id, activity_date, last_action_at)
SELECT user_id, substr(created_at, 1, 10), created_at
FROM jobs
WHERE user_id IS NOT NULL AND user_id > 0;
