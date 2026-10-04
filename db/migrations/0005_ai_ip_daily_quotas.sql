-- 0005: pseudonymous UTC-day quota per client IP (HMAC digest, not plaintext IP).
-- Global + per-client reservations commit or roll back together in one transaction.
CREATE TABLE ai_ip_daily_quotas (
    day_utc DATE NOT NULL,
    client_hash CHAR(64) NOT NULL,
    used_requests INTEGER NOT NULL CHECK (used_requests >= 0),
    PRIMARY KEY (day_utc, client_hash)
);
