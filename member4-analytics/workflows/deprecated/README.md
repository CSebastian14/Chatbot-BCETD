# Deprecated Workflows — Member 4

This folder contains the original analytics logging sub-workflow that was retired when the query pipeline switched to a direct PostgreSQL INSERT pattern.

## Architectural change

### Original design (deprecated)

A dedicated sub-workflow `BCETD - Analytics Logging` was called via n8n's Execute Workflow node at the end of each query in `03_student_query_pipeline`. The sub-workflow received the analytics payload, normalized fields, hashed the query, and performed the INSERT into PostgreSQL.

### Current design (active)

The INSERT is performed directly by a Postgres node in the main query pipeline. After the `Format Response + Analytics` node splits its output into a response branch and an analytics branch, the analytics branch goes straight to two Postgres nodes:

1. **Insert into `query_logs`** — main row with query_hash, category, match_score, response_ms, etc.
2. **Upsert `document_usage`** — increments reference count for each cited source

Both nodes have `Continue On Fail: ON` so a database error never affects the student's response.

## Why this change was made

| Property | Sub-workflow (deprecated) | Direct INSERT (active) |
|----------|---------------------------|------------------------|
| Failure points per query | 4 (input mapping, trigger, normalize, SQL) | 1 (SQL only) |
| Latency overhead | ~50-200 ms (internal n8n call) | 0 ms |
| Workflows to maintain | 2 (main + sub) | 1 (main only) |
| Debug surface | Cross-workflow tracing | Single workflow |
| Configuration drift risk | High (parameter mapping in two places) | None |

For a project of this scale, the architectural modularity of a sub-workflow did not justify its operational complexity. The direct INSERT delivers identical functional behavior with significantly lower mean time to recovery when issues occur.

## What remains in Member 4 (still active)

The deprecation applies only to the **logging sub-workflow**. Member 4 continues to own:

- `../workflow_analytics_api.json` — 5 webhook endpoints that expose dashboard data
- `../workflow_daily_stats.json` — cron-scheduled daily aggregation + 90-day retention purge
- `../../sql/001_initial_schema.sql` — PostgreSQL schema (tables, views, functions)
- `../../scripts/backup_database.sh` — daily backup with rotation
- `../../grafana_dashboard.json` — 9-panel pre-built dashboard

The schema, dashboard, and aggregation logic did not change — only the path by which rows arrive at the database.

## Files in this folder

- `workflow_analytics_logging.json` — original sub-workflow that wrapped the INSERT in normalization logic

## Policy

- Do not import this workflow into a live n8n instance.
- The functionality is fully replaced by the Postgres nodes at the end of `member2-rag-pipeline/workflows/03_student_query_pipeline.json`.
