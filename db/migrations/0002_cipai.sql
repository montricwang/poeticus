-- 迁移 0002：明确此字段记录的是词牌，而非宫调。
-- 重命名保留已有 3491 条记录、UUID 和外键引用。
ALTER TABLE poems RENAME COLUMN tune TO cipai;
ALTER INDEX idx_poems_tune_order RENAME TO idx_poems_cipai_order;
