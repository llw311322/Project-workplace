-- ============================================
-- 魔饮咖啡内部业务工作台 - PostgreSQL 初始化脚本
-- 版本: PostgreSQL 16+ ， pgvector 扩展
-- 执行方式: docker 启动 postgres 时自动加载，或手动 psql -f 执行
-- ============================================

-- 1. 启用 pgvector 扩展（向量检索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 用户表
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(64)  UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(16)  NOT NULL CHECK (role IN ('submitter', 'approver')),
    display_name    VARCHAR(64),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role    ON users(role);

-- 3. 单据表（货品申领）
-- 状态流转: draft → submitted → approving → approved / rejected
CREATE TABLE IF NOT EXISTS documents (
    id              BIGSERIAL PRIMARY KEY,
    submitter_id    BIGINT       NOT NULL REFERENCES users(id),
    title           VARCHAR(255) NOT NULL,
    -- 货品明细: [{name, spec, quantity, unit_price}]
    items           JSONB        NOT NULL DEFAULT '[]'::jsonb,
    remark          TEXT,
    status          VARCHAR(16)  NOT NULL
                    CHECK (status IN ('draft', 'submitted', 'approving', 'approved', 'rejected')),
    -- AI 自动生成的单据摘要（可选，Agent 失败时为 NULL）
    summary         TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_submitter ON documents(submitter_id);
CREATE INDEX IF NOT EXISTS idx_documents_status    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created   ON documents(created_at DESC);

-- 4. 审批记录表（每一步审批留痕）
CREATE TABLE IF NOT EXISTS approval_records (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT       NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    approver_id     BIGINT       NOT NULL REFERENCES users(id),
    action          VARCHAR(16)  NOT NULL CHECK (action IN ('approve', 'reject', 'resubmit', 'withdraw')),
    comment         TEXT,
    -- 审批时的状态快照，便于追溯
    from_status     VARCHAR(16),
    to_status       VARCHAR(16),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_doc   ON approval_records(document_id);
CREATE INDEX IF NOT EXISTS idx_approval_approver ON approval_records(approver_id);

-- 5. pgvector 向量表（RAG 知识库：门店制度、产品资料）
--    embedding 维度与 rag/embedder.py 的 EMBEDDING_DIM 保持一致：
--    通义 text-embedding-v3 默认 1024 维
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              BIGSERIAL PRIMARY KEY,
    content         TEXT         NOT NULL,
    embedding       vector(1024),
    metadata        JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- {type, source, ...}
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_metadata ON knowledge_chunks USING GIN (metadata);
-- 向量相似度索引：HNSW 适合小数据量（免训练、召回稳）；
-- 数据量上到百万级再考虑换 ivfflat (vector_cosine_ops, lists=...)
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops);

-- 6. 初始种子数据：1 个提交人 + 1 个审批人
-- 此处写入的是占位 hash，无法通过登录校验；真实使用请用
-- passlib[bcrypt] 生成哈希后 UPDATE，或改走应用侧的注册/初始化流程
INSERT INTO users (username, password_hash, role, display_name) VALUES
    ('submitter01', '$2b$12$placeholder_hash_1', 'submitter', '张三（提交人）'),
    ('approver01',  '$2b$12$placeholder_hash_2', 'approver',  '李四（审批人）')
ON CONFLICT (username) DO NOTHING;

-- 7. 更新时间触发器（自动维护 updated_at 字段）
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at     ON users;
DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
