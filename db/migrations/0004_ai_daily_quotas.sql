-- 迁移 0004：为匿名公开 AI 请求建立持久化的 UTC 自然日额度。
-- 每天一条记录。在调用模型前预占额度，即使浏览器断开连接，
-- 或上游模型调用失败，也不会退还本次额度。
CREATE TABLE ai_daily_quotas (
    day_utc DATE PRIMARY KEY,
    used_requests INTEGER NOT NULL CHECK (used_requests >= 0)
);
