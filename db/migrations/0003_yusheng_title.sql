-- 迁移 0003：重命名贺铸自创寓声题头字段。
-- 保留现有记录、UUID 和来源追溯信息。
ALTER TABLE poems RENAME COLUMN yusheng TO yusheng_title;
