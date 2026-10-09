-- 迁移 0005：以 HMAC 摘要而非明文 IP 记录各客户端的 UTC 日额度。
-- 全站与单客户端额度在同一事务中一起提交或回滚。
CREATE TABLE ai_ip_daily_quotas (
    day_utc DATE NOT NULL,
    client_hash CHAR(64) NOT NULL,
    used_requests INTEGER NOT NULL CHECK (used_requests >= 0),
    PRIMARY KEY (day_utc, client_hash)
);
