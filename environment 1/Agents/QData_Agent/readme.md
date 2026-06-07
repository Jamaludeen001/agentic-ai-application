QData_Agent/
│
├── server.py                    # MCP server — exposes all tools
├── client.py                    # MCP client — connects to server, runs agent
│
├── tools/                       # each tool as a package
│   ├── __init__.py
│   ├── schema_inspector/
│   │   ├── __init__.py
│   │   └── tool.py              # _inspect_source_schema logic
│   ├── source_query/
│   │   ├── __init__.py
│   │   └── tool.py              # _query_source logic
│   ├── temp_loader/
│   │   ├── __init__.py
│   │   └── tool.py              # _load_source_into_temp logic
│   ├── temp_query/
│   │   ├── __init__.py
│   │   └── tool.py              # _query_temp logic
│   └── temp_inspector/
│       ├── __init__.py
│       └── tool.py              # _list_temp_tables logic
│
├── core/
│   ├── __init__.py
│   ├── validators.py            # AST SQL validation
│   ├── pathguard.py             # path traversal guard
│   └── duckdb_runner.py         # all DuckDB execution
│
├── agent/
│   ├── __init__.py
│   ├── agent.py                 # FullyCustomAgent class
│   ├── audit.py                 # LangSmithAudit class
│   └── classifier.py            # intent classifier
│
└── config.py                    # all env vars, folder paths
