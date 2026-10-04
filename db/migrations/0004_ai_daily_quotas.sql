-- 0004: persisted UTC-day reservation for anonymous public AI.
-- One row per day. A request slot is spent before calling the model, even if
-- the browser disconnects or the upstream model fails.
CREATE TABLE ai_daily_quotas (
    day_utc DATE PRIMARY KEY,
    used_requests INTEGER NOT NULL CHECK (used_requests >= 0)
);
