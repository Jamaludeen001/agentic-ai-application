# QData Agent

> A fully custom, production-ready data analyst agent that queries CSV files securely
> through a Model Context Protocol (MCP) server — no LangChain AgentExecutor, no black box.

---

## Why QData Agent?

Most agents are built on framework abstractions that hide what's really happening.
QData Agent owns every layer:

- **Custom agent loop** — no AgentExecutor, full control over every decision
- **AST-level SQL validation** — not keyword filtering, actual parse tree analysis
- **MCP architecture** — tools live as an independent Streamable HTTP service
- **Source/temp separation** — source CSV is immutable, agent works in sandbox
- **Full audit trail** — every run, every tool call traced in LangSmith

---

## Architecture

```
client.py
    │
    │  Streamable HTTP + Bearer Token
    ▼
server.py (MCP Server — http://localhost:8000/mcp)
    │
    ├── tool_inspect_source_schema
    ├── tool_query_source              ← AST validated, SELECT only
    ├── tool_load_source_into_temp
    ├── tool_query_temp                ← sandboxed, source never touched
    └── tool_list_temp_tables
    │
    ▼
tools/          ← each tool as an isolated package
core/           ← validators, pathguard, duckdb runner
agent/          ← custom loop, audit, classifier
config.py       ← single source of truth
```

---

## Project Structure

```
QData_Agent/
│
├── server.py                    # MCP server — exposes all tools over Streamable HTTP
├── client.py                    # MCP client — connects to server, runs agent loop
│
├── tools/
│   ├── schema_inspector/
│   │   └── tool.py              # inspect CSV column names and data types
│   ├── source_query/
│   │   └── tool.py              # READ-ONLY SELECT on source CSV
│   ├── temp_loader/
│   │   └── tool.py              # load source CSV into temp sandbox
│   ├── temp_query/
│   │   └── tool.py              # run ANY SQL in temp sandbox
│   └── temp_inspector/
│       └── tool.py              # list all tables in temp sandbox
│
├── core/
│   ├── validators.py            # AST-level SQL validation via sqlglot
│   ├── pathguard.py             # path traversal guard
│   └── duckdb_runner.py         # all DuckDB execution logic
│
├── agent/
│   ├── agent.py                 # fully custom agent loop
│   ├── audit.py                 # LangSmith audit logger
│   └── classifier.py            # intent classifier for feedback detection
│
├── config.py                    # all env vars and folder paths
├── .env.example                 # environment variable template
└── requirements.txt
```

---

## Security Layers

| Layer | How |
|---|---|
| AST-level SQL validation | sqlglot parses SQL into syntax tree — mutations blocked at parse time, not by keywords |
| Source / temp separation | Source CSV is a read-only view — agent sandbox is a separate DuckDB session |
| Path traversal guard | Resolved path checked against allowed folder before every file access |
| Bearer token auth | Every MCP request requires `Authorization: Bearer <token>` header |
| Session isolation | Each conversation gets its own DuckDB `.db` file in temp folder |
| Session cleanup | Temp database wiped automatically when conversation ends |

---

## How the Agent Thinks

```
User: "What are the top 5 products by revenue in sales.csv?"

Step 1 → tool_inspect_source_schema("sales.csv")
       ← product_name (VARCHAR), revenue (DOUBLE), region (VARCHAR)

Step 2 → tool_query_source("sales.csv",
            "SELECT product_name, SUM(revenue) as total
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

Edit `.env`:

```
OPENAI_API_KEY=your-openai-api-key
LANGCHAIN_API_KEY=your-langsmith-api-key
MCP_AUTH_TOKEN=your-secret-token
MCP_SERVER_URL=http://localhost:8000/mcp
```

**3. Add your CSV files**

```bash
mkdir -p data/source
cp your_file.csv data/source/
```

**4. Start MCP server**

```bash
python server.py

# QData MCP Server starting...
# Endpoint     : http://0.0.0.0:8000/mcp
# Health check : http://0.0.0.0:8000/health
# Transport    : Streamable HTTP
```

**5. Start the agent**

```bash
python client.py

# Session    : abc-123...
# MCP Server : http://localhost:8000/mcp
# Connecting to MCP server...
#
# Tools available from server (5):
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

## Requirements

```
python >= 3.11
openai
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
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key |
| `MCP_AUTH_TOKEN` | Yes | Bearer token for MCP server auth |
| `MCP_SERVER_URL` | Yes | MCP server endpoint URL |
| `LANGCHAIN_PROJECT` | No | LangSmith project name (default: `dataforge`) |

---

## What's Not Included (intentionally)

This project is intentionally kept minimal and auditable. The following are
out of scope until the foundation is fully tested:

- RAG / vector search
- Web UI
- Multi-agent orchestration
- Docker deployment
- PostgreSQL / cloud database

---

## License

MIT
