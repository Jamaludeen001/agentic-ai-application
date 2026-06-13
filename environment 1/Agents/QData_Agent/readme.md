# QData Agent

> A fully custom, production-ready data analyst agent architected from the ground up — no LangChain AgentExecutor, no black box. Powered by MCP for tool orchestration, secured with JWT authentication (AWS KMS in production, local secret in dev), supports both CSV (dev) and Amazon Redshift (prod) as data sources, fully observable via LangSmith with per-run audit trails and user feedback scoring, and an LLM-based intent classifier that understands natural conversation. Every layer is owned, auditable, and production-hardened.

---

## Why QData Agent?

Most agents are built on framework abstractions that hide what's really happening.
QData Agent owns every layer:

- **Custom agent loop** — no AgentExecutor, full control over every decision
- **AST-level SQL validation** — not keyword filtering, actual parse tree analysis
- **MCP architecture** — tools live as an independent Streamable HTTP service
- **Dev / Prod parity** — CSV + DuckDB for dev, Amazon Redshift for prod
- **JWT authentication** — local HS256 secret for dev, AWS KMS RS256 for prod
- **Source / temp separation** — source data is immutable, agent works in sandbox
- **Full audit trail** — every run, every tool call traced in LangSmith

---

## Architecture

```
client.py
    │
    │  Streamable HTTP + JWT (HS256 dev / RS256 prod)
    ▼
server.py (MCP Server — http://localhost:8000/mcp)
    │
    ├── tool_inspect_source_schema   ← CSV schema (dev) / Redshift schema (prod)
    ├── tool_query_source            ← AST validated, SELECT only
    ├── tool_load_source_into_temp
    ├── tool_query_temp              ← sandboxed DuckDB, source never touched
    └── tool_list_temp_tables
    │
    ▼
tools/          ← each tool as an isolated package
core/           ← validators, pathguard, duckdb runner, redshift runner
agent/          ← custom loop, audit, classifier
auth/           ← JWT handler (KMS prod / local dev)
config.py       ← single source of truth, ENV flag switches dev/prod
```

---

## Project Structure

```
QData_Agent/
│
├── server.py                        # MCP server — exposes all tools over Streamable HTTP
├── client.py                        # MCP client — connects to server, runs agent loop
│
├── tools/
│   ├── schema_inspector/
│   │   └── tool.py                  # CSV schema (dev) / Redshift schema (prod)
│   ├── source_query/
│   │   └── tool.py                  # READ-ONLY SELECT — DuckDB (dev) / Redshift (prod)
│   ├── temp_loader/
│   │   └── tool.py                  # load source data into temp DuckDB sandbox
│   ├── temp_query/
│   │   └── tool.py                  # run ANY SQL in temp sandbox (always DuckDB)
│   └── temp_inspector/
│       └── tool.py                  # list all tables in temp sandbox
│
├── core/
│   ├── validators.py                # AST-level SQL validation via sqlglot
│   ├── pathguard.py                 # path traversal guard (dev)
│   ├── duckdb_runner.py             # DuckDB execution — CSV queries + temp sandbox
│   └── redshift_runner.py           # Redshift execution — prod SSO connection
│
├── agent/
│   ├── agent.py                     # fully custom agent loop with scratchpad
│   ├── audit.py                     # LangSmith audit — every run + tool call logged
│   └── classifier.py                # LLM-based intent classifier
│
├── auth/
│   ├── __init__.py
│   └── jwt_handler.py               # HS256 local (dev) / RS256 KMS (prod)
│
├── config.py                        # all env vars, ENV flag, folder paths
├── .env.example                     # environment variable template
└── requirements.txt
```

---

## Dev vs Production

| | Dev | Production |
|---|---|---|
| Data source | CSV files via DuckDB | Amazon Redshift (SSO) |
| JWT signing | HS256 local secret | RS256 AWS KMS |
| Permissions | Path traversal guard | Redshift native (SSO enforces) |
| Temp sandbox | DuckDB | DuckDB |
| AST validation | ✅ | ✅ |
| LangSmith audit | ✅ | ✅ |
| Switch | `ENV=dev` | `ENV=prod` |

---

## Security Layers

| Layer | How |
|---|---|
| AST-level SQL validation | sqlglot parses SQL into syntax tree — mutations blocked at parse time, not by keywords |
| Source / temp separation | Source data is read-only — agent sandbox is a separate isolated DuckDB session |
| Path traversal guard | Resolved path checked against allowed folder before every file access (dev) |
| JWT authentication | Every MCP request requires signed JWT — HS256 (dev) or KMS RS256 (prod) |
| Redshift SSO | Prod queries run as the actual user — Redshift enforces table permissions natively |
| Session isolation | Each conversation gets its own DuckDB `.db` file in temp folder |
| Session cleanup | Temp database wiped automatically when conversation ends |

---

## How the Agent Thinks

```
User: "What are the top 5 products by revenue in sales.csv?"

Step 1 → tool_inspect_source_schema("sales.csv")
       ← product_name (VARCHAR), revenue (DOUBLE), region (VARCHAR)

Step 2 → tool_query_source(
            filename="sales.csv",
            sql="SELECT product_name, SUM(revenue) as total
                 FROM data GROUP BY product_name
                 ORDER BY total DESC LIMIT 5")
       ← results table

Final  → "The top 5 products by revenue are: ..."
```

No magic. Every step is visible, logged, and traceable.

---

## Observability

Every conversation turn is fully traced in LangSmith:

```
Run (chain)
 ├── tool_inspect_source_schema     (tool)
 ├── tool_query_source              (tool)
 └── Final answer                   (output)
```

- Every tool call logged as a child run under the parent trace
- User feedback tied to `run_id` — thumbs up scores `1.0`, thumbs down `0.0`
- Session ID threads through every trace for full conversation audit
- Termination reason recorded — `final_answer`, `max_steps`, or error

---

## Quickstart

**1. Clone and install**

```bash
git clone https://github.com/yourusername/QData_Agent.git
cd QData_Agent
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` for dev:

```
ENV=dev
OPENAI_API_KEY=your-openai-api-key
LANGCHAIN_API_KEY=your-langsmith-api-key
JWT_SECRET=generate-with-python-secrets-token-hex-32
MCP_SERVER_URL=http://localhost:8000/mcp
LANGCHAIN_PROJECT=QData_Agent
```

**3. Add your CSV files (dev)**

```bash
mkdir -p data/source
cp your_file.csv data/source/
```

**4. Start MCP server**

```bash
python server.py

# QData Agent MCP Server starting...
# Endpoint     : http://0.0.0.0:8000/mcp
# Health check : http://0.0.0.0:8000/health
# Transport    : Streamable HTTP
# Auth         : JWT (Local HS256)
# Data source  : CSV (DuckDB)
```

**5. Start the agent**

```bash
python client.py

# Session    : abc-123...
# MCP Server : http://localhost:8000/mcp
# Mode       : Dev (CSV)
# Source     : ./data/source
#
# Tools available (5):
#   - tool_inspect_source_schema
#   - tool_query_source
#   - tool_load_source_into_temp
#   - tool_query_temp
#   - tool_list_temp_tables
#
# You:
```

---

## Example Queries

```
You: what columns are in sales.csv?
You: show me top 10 rows from sales.csv
You: what is the total revenue by region in sales.csv?
You: join sales.csv and customers.csv and show lifetime value per customer
You: good one thanks          ← agent detects positive feedback, logs to LangSmith
You: that's wrong             ← agent detects negative feedback, logs to LangSmith
You: exit                     ← session cleaned up, temp db wiped
```

---

## Environment Variables

### Dev

| Variable | Required | Description |
|---|---|---|
| `ENV` | Yes | Set to `dev` |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key |
| `JWT_SECRET` | Yes | Min 32 char secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MCP_SERVER_URL` | Yes | MCP server endpoint URL |
| `LANGCHAIN_PROJECT` | No | LangSmith project name (default: `QData_Agent`) |

### Production

| Variable | Required | Description |
|---|---|---|
| `ENV` | Yes | Set to `prod` |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key |
| `KMS_KEY_ID` | Yes | AWS KMS key ARN for JWT RS256 signing |
| `REDSHIFT_HOST` | Yes | Redshift cluster endpoint |
| `REDSHIFT_DATABASE` | Yes | Redshift database name |
| `REDSHIFT_PORT` | No | Redshift port (default: `5439`) |
| `MCP_SERVER_URL` | Yes | MCP server endpoint URL |
| `ISSUER` | No | JWT issuer (default: `qdataagent-client`) |
| `AUDIENCE` | No | JWT audience (default: `qdataagent-mcp-server`) |
| `ACCESS_TTL` | No | JWT expiry in seconds (default: `3600`) |
| `LANGCHAIN_PROJECT` | No | LangSmith project name (default: `QData_Agent`) |

---

## Requirements

```
python >= 3.11
langchain-openai
langsmith
mcp
fastmcp
uvicorn
duckdb
sqlglot
pandas
json-repair
python-dotenv
starlette
pyjwt
boto3
redshift-connector
fastapi
python-multipart
argon2-cffi
```

---

## What's Not Included (intentionally)

This project is intentionally kept minimal and auditable. The following are
out of scope until the foundation is fully tested:

- RAG / vector search
- Web UI
- Multi-agent orchestration
- Docker deployment

---

## License

MIT
