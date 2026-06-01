# Member 2 — n8n Workflows

This folder contains all n8n workflows that power the RAG pipeline (Retrieval-Augmented Generation) of the BCETD chatbot.

## Workflow inventory

| File | Purpose | Trigger |
|------|---------|---------|
| `01_web_api_ingestion.json` | Scrapes pages and news from the ULBS website via REST API, splits text into chunks, generates embeddings, and inserts them into the Qdrant vector database. | Manual execution (run periodically — monthly recommended) |
| `02_insert_page_to_qdrant.json` | Sub-workflow called by `01` for inserting individual chunks into Qdrant with metadata. | Called by `01` |
| `03_student_query_pipeline.json` | Receives student queries via webhook, validates input, calls the AI Agent (with vector search tool), formats the response with sources, and logs analytics. | Webhook `/webhook/chat` (called by the Flask frontend) |

## Import procedure

### First-time setup

1. Open n8n in the browser: `http://localhost:5678`
2. Log in with the credentials from `.env`
3. **Workflows** → click the dropdown next to **Add workflow** → **Import from File**
4. Import the 3 workflows in this order: `01`, `02`, `03`
5. For each imported workflow, configure the required credentials:
   - **OpenAI** (using the API key from `.env`)
   - **Qdrant** (URL: `http://qdrant:6333`)
   - **PostgreSQL** (host: `postgres`, credentials from `.env`)
6. **Activate** workflow `03_student_query_pipeline.json` (Active toggle ON)
7. Workflow `01_web_api_ingestion.json` remains **inactive** — it is run manually when re-indexing

### After modifications in n8n

If a workflow is modified directly in the n8n UI (which is the normal way to edit), export the new version to keep this folder in sync:

1. Open the workflow in n8n
2. Menu (3 dots, top-right) → **Download**
3. Save the JSON file with the existing name (overwrite)
4. Commit the change to Git

## Configuration applied to active workflows

These parameters have been tuned through testing and should be preserved:

### Workflow `01_web_api_ingestion`

- **Text Splitter** (Recursive Character): chunk size `800`, overlap `100`
- **Filter Junk** (Code node): minimum content length `80` characters, no rejection of structured tables
- **Qdrant Collection**: `ulbs_documents`
- **Embeddings Model**: `text-embedding-3-small` (1536 dimensions, Cosine)

### Workflow `03_student_query_pipeline`

- **AI Agent2**:
  - Max Iterations: `5`
  - Memory: Simple Memory (context window 3)
- **OpenAI Chat Model2**:
  - Model: `gpt-4o-mini`
  - Temperature: `0.2`
  - Max Tokens: `400`
- **university_documents_search1** (Qdrant Tool):
  - Operation Mode: `Retrieve Documents (As Tool for AI Agent)`
  - Limit: `3`
  - Content Payload Key: `content`

The full system message used by the AI Agent is documented in `../SYSTEM_PROMPT_DOCUMENTATION.md`.

## Why workflows are stored as JSON files in Git

The n8n container holds the live, executing workflows in its internal database. The JSONs in this folder are **versioned backups** that allow:

- Recovery if a workflow is accidentally broken in the UI
- Reproducible deployments to new environments (clone + import)
- Code review of workflow changes through Git diffs
- Onboarding new team members

The JSONs are **not loaded at runtime by Flask or any other service**. They are imported manually into n8n through the UI.

## Re-indexing the document corpus

When the ULBS website content changes (new programs, updated regulations, new news items), refresh the Qdrant index:

```bash
# 1. Delete the existing collection
curl -X DELETE http://localhost:6333/collections/ulbs_documents

# 2. In n8n UI, open workflow 01_web_api_ingestion and click "Execute workflow"
# Wait 2-5 minutes for completion

# 3. Verify the result
curl http://localhost:6333/collections/ulbs_documents
# Expected: points_count between 150 and 300
```

This process does not interrupt the chat — students will receive answers based on the previous index until the new one is built (then it switches atomically when the collection is recreated).
