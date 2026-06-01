-- ═══════════════════════════════════════════════════════════════
-- CHATBOT BCETD — PostgreSQL Schema Migration v1.0
-- Member 4 Deliverable: Analytics & Database Engineer
-- 
-- Database: chatbot_stats (set via POSTGRES_DB env variable)
-- Run: psql -h localhost -U chatbot_user -d chatbot_stats -f 001_initial_schema.sql
-- ═══════════════════════════════════════════════════════════════

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ───────────────────────────────────────────────────
-- TABLE: query_logs
-- Core analytics table — stores anonymized query data
-- ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_logs (
    id              SERIAL PRIMARY KEY,
    query_hash      VARCHAR(64)     NOT NULL,       -- SHA-256 of normalized query (never raw text)
    category        VARCHAR(20)     NOT NULL        -- ACADEMIC, ADMIN, REJECTED, UNANSWERED, OFF_TOPIC, INAPPROPRIATE
                    CHECK (category IN ('ACADEMIC','ADMINISTRATIVE','REJECTED','UNANSWERED','OFF_TOPIC','INAPPROPRIATE','ERROR')),
    match_score     DECIMAL(4,3)    DEFAULT 0.000   -- Top retrieval relevance score (0.000–1.000)
                    CHECK (match_score >= 0 AND match_score <= 1),
    response_ms     INTEGER         DEFAULT 0       -- End-to-end response time in milliseconds
                    CHECK (response_ms >= 0),
    docs_matched    TEXT[]          DEFAULT '{}',    -- Array of matched document filenames
    was_answered    BOOLEAN         NOT NULL DEFAULT FALSE,  -- Did the bot provide a substantive answer?
    session_id      UUID            NOT NULL,        -- Rotating hourly; no persistent tracking
    rejection_layer VARCHAR(20)     DEFAULT NULL,    -- Which guardrail layer rejected (L1_INJECTION, L2_OFFTOPIC, etc.)
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────────────
-- INDEXES for dashboard query performance
-- ───────────────────────────────────────────────────

-- Time-based queries (daily/weekly/monthly reports)
CREATE INDEX idx_query_logs_created_at ON query_logs (created_at DESC);

-- Category breakdown queries
CREATE INDEX idx_query_logs_category ON query_logs (category);

-- Failure rate queries (answered vs unanswered)
CREATE INDEX idx_query_logs_was_answered ON query_logs (was_answered);

-- Composite: time + category for filtered reports
CREATE INDEX idx_query_logs_time_category ON query_logs (created_at DESC, category);

-- Repeated questions detection
CREATE INDEX idx_query_logs_query_hash ON query_logs (query_hash);

-- Session grouping
CREATE INDEX idx_query_logs_session ON query_logs (session_id);

-- ───────────────────────────────────────────────────
-- TABLE: document_usage
-- Tracks which documents are referenced most often
-- ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_usage (
    id              SERIAL PRIMARY KEY,
    document_name   VARCHAR(255)    NOT NULL,
    reference_count INTEGER         NOT NULL DEFAULT 0,
    last_referenced TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    first_seen      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_document_usage_name ON document_usage (document_name);

-- ───────────────────────────────────────────────────
-- TABLE: daily_stats (materialized summary)
-- Pre-computed daily aggregates for fast dashboard loading
-- ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_stats (
    stat_date           DATE PRIMARY KEY,
    total_queries       INTEGER     NOT NULL DEFAULT 0,
    answered_count      INTEGER     NOT NULL DEFAULT 0,
    unanswered_count    INTEGER     NOT NULL DEFAULT 0,
    rejected_count      INTEGER     NOT NULL DEFAULT 0,
    avg_response_ms     INTEGER     DEFAULT 0,
    avg_match_score     DECIMAL(4,3) DEFAULT 0.000,
    top_category        VARCHAR(20),
    unique_sessions     INTEGER     DEFAULT 0,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────────────
-- TABLE: hourly_session_map
-- Manages rotating session IDs
-- ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hourly_session_map (
    hour_key        VARCHAR(13) PRIMARY KEY,    -- Format: YYYY-MM-DD-HH
    session_uuid    UUID NOT NULL DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────────────
-- FUNCTION: Get or create hourly session ID
-- Returns the same UUID for the entire hour, then
-- generates a new one when the hour changes
-- ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_hourly_session()
RETURNS UUID AS $$
DECLARE
    current_hour VARCHAR(13);
    result_uuid UUID;
BEGIN
    current_hour := TO_CHAR(NOW(), 'YYYY-MM-DD-HH24');
    
    INSERT INTO hourly_session_map (hour_key, session_uuid)
    VALUES (current_hour, gen_random_uuid())
    ON CONFLICT (hour_key) DO NOTHING;
    
    SELECT session_uuid INTO result_uuid
    FROM hourly_session_map
    WHERE hour_key = current_hour;
    
    RETURN result_uuid;
END;
$$ LANGUAGE plpgsql;

-- ───────────────────────────────────────────────────
-- FUNCTION: Compute daily stats
-- Run via cron or n8n scheduled workflow at midnight
-- ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION compute_daily_stats(target_date DATE DEFAULT CURRENT_DATE - INTERVAL '1 day')
RETURNS VOID AS $$
BEGIN
    INSERT INTO daily_stats (
        stat_date, total_queries, answered_count, unanswered_count,
        rejected_count, avg_response_ms, avg_match_score,
        top_category, unique_sessions
    )
    SELECT
        target_date,
        COUNT(*),
        COUNT(*) FILTER (WHERE was_answered = TRUE),
        COUNT(*) FILTER (WHERE was_answered = FALSE AND category NOT IN ('REJECTED','OFF_TOPIC','INAPPROPRIATE')),
        COUNT(*) FILTER (WHERE category IN ('REJECTED','OFF_TOPIC','INAPPROPRIATE')),
        COALESCE(AVG(response_ms)::INTEGER, 0),
        COALESCE(AVG(match_score), 0),
        (SELECT category FROM query_logs
         WHERE created_at::DATE = target_date
         GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1),
        COUNT(DISTINCT session_id)
    FROM query_logs
    WHERE created_at::DATE = target_date
    ON CONFLICT (stat_date) DO UPDATE SET
        total_queries = EXCLUDED.total_queries,
        answered_count = EXCLUDED.answered_count,
        unanswered_count = EXCLUDED.unanswered_count,
        rejected_count = EXCLUDED.rejected_count,
        avg_response_ms = EXCLUDED.avg_response_ms,
        avg_match_score = EXCLUDED.avg_match_score,
        top_category = EXCLUDED.top_category,
        unique_sessions = EXCLUDED.unique_sessions,
        computed_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ───────────────────────────────────────────────────
-- FUNCTION: Purge old data (retention policy)
-- Deletes query_logs older than 90 days
-- Keeps daily_stats forever (aggregated, tiny)
-- ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION purge_old_data(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM query_logs
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    -- Also clean up old session mappings
    DELETE FROM hourly_session_map
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ───────────────────────────────────────────────────
-- ANALYTICS VIEWS for Grafana / Admin Dashboard
-- ───────────────────────────────────────────────────

-- View: Daily query volume (last 30 days)
CREATE OR REPLACE VIEW v_daily_volume AS
SELECT
    created_at::DATE AS day,
    COUNT(*) AS total_queries,
    COUNT(*) FILTER (WHERE was_answered) AS answered,
    COUNT(*) FILTER (WHERE NOT was_answered) AS unanswered,
    ROUND(100.0 * COUNT(*) FILTER (WHERE was_answered) / NULLIF(COUNT(*), 0), 1) AS success_rate_pct
FROM query_logs
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY created_at::DATE
ORDER BY day DESC;

-- View: Category breakdown
CREATE OR REPLACE VIEW v_category_breakdown AS
SELECT
    category,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER(), 0), 1) AS percentage,
    ROUND(AVG(response_ms)) AS avg_response_ms
FROM query_logs
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY category
ORDER BY count DESC;

-- View: Top referenced documents
CREATE OR REPLACE VIEW v_top_documents AS
SELECT
    document_name,
    reference_count,
    last_referenced
FROM document_usage
ORDER BY reference_count DESC
LIMIT 20;

-- View: Hourly usage pattern (for peak hours analysis)
CREATE OR REPLACE VIEW v_hourly_pattern AS
SELECT
    EXTRACT(HOUR FROM created_at) AS hour_of_day,
    COUNT(*) AS query_count,
    ROUND(AVG(response_ms)) AS avg_response_ms
FROM query_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM created_at)
ORDER BY hour_of_day;

-- View: Failure analysis
CREATE OR REPLACE VIEW v_failure_analysis AS
SELECT
    COALESCE(rejection_layer, 'NO_MATCH') AS failure_type,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER(), 0), 1) AS percentage
FROM query_logs
WHERE was_answered = FALSE
AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY rejection_layer
ORDER BY count DESC;

-- View: Repeated questions (by hash frequency)
CREATE OR REPLACE VIEW v_repeated_questions AS
SELECT
    query_hash,
    COUNT(*) AS ask_count,
    MAX(category) AS typical_category,
    ROUND(AVG(match_score), 3) AS avg_score,
    BOOL_OR(was_answered) AS ever_answered,
    MIN(created_at) AS first_asked,
    MAX(created_at) AS last_asked
FROM query_logs
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY query_hash
HAVING COUNT(*) >= 3
ORDER BY ask_count DESC
LIMIT 50;

-- ───────────────────────────────────────────────────
-- Grant permissions (adjust user as needed)
-- ───────────────────────────────────────────────────
-- GRANT SELECT, INSERT ON query_logs TO n8n_user;
-- GRANT SELECT, INSERT, UPDATE ON document_usage TO n8n_user;
-- GRANT SELECT ON v_daily_volume, v_category_breakdown, v_top_documents, 
--     v_hourly_pattern, v_failure_analysis, v_repeated_questions TO grafana_user;

-- ═══════════════════════════════════════════════════════════════
-- END OF MIGRATION v1.0
-- ═══════════════════════════════════════════════════════════════
