-- 未来独立 Poem Retrieval PostgreSQL 的关系表模板。
-- 不适用于阅读语料库 poems 的现有迁移。
-- 此表记录 Werneror 的完整逐字拼接与格式归一化完整拼接关系，不修改原始作品。

CREATE TABLE IF NOT EXISTS retrieval_work_compositions (
    parent_work_id TEXT NOT NULL,
    member_work_id TEXT NOT NULL,
    member_order INTEGER NOT NULL CHECK (member_order >= 1),
    start_char INTEGER NOT NULL CHECK (start_char >= 0),
    end_char INTEGER NOT NULL CHECK (end_char > start_char),
    match_kind TEXT NOT NULL CHECK (match_kind IN ('exact_concatenation', 'normalized_concatenation')),
    PRIMARY KEY (parent_work_id, member_order),
    CHECK (parent_work_id <> member_work_id)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_work_compositions_member
    ON retrieval_work_compositions (member_work_id);

-- CSV 列的顺序与 export_work_compositions.py 的 CSV_COLUMNS 一致。
-- PostgreSQL 导入前核对 manifest 中的 corpus_sha256。
-- 通过参数查询关系（当前独立诗篇 -> 包含它的合集）：
-- SELECT DISTINCT parent_work_id FROM retrieval_work_compositions
-- WHERE member_work_id = $1;
-- 反向（合集 -> 各成员）：
-- SELECT member_work_id, member_order, start_char, end_char
-- FROM retrieval_work_compositions
-- WHERE parent_work_id = $1 ORDER BY member_order;
