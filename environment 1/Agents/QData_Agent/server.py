import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from tools.schema_inspector.tool import inspect_source_schema
from tools.source_query.tool import query_source
from tools.temp_loader.tool import load_source_into_temp
from tools.temp_query.tool import query_temp
from tools.temp_inspector.tool import list_temp_tables
from config import MCP_AUTH_TOKEN

# ── Token Auth ────────────────────────────────────────────────────────────────
class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code = 401,
                content     = {"error": "Missing Authorization header. Use: Bearer <token>"}
            )
        token = auth_header.split("Bearer ")[-1].strip()
        if token != MCP_AUTH_TOKEN:
            return JSONResponse(
                status_code = 403,
                content     = {"error": "Invalid token."}
            )
        return await call_next(request)

# ── MCP Server ────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name = "QData_Agent",
    host = "0.0.0.0",
    port = 8000,
)

@mcp.tool()
def tool_inspect_source_schema(filename: str) -> str:
    """
    Inspect column names and data types of a source CSV file.
    Always call this FIRST before writing any query.
    Input: filename only (e.g. 'sales.csv')
    """
    return inspect_source_schema(filename)

@mcp.tool()
def tool_query_source(filename: str, sql: str) -> str:
    """
    Run a READ-ONLY SELECT query on source CSV.
    Table always named 'data'. Only SELECT/WITH/EXPLAIN allowed.
    """
    return query_source(filename, sql)

@mcp.tool()
def tool_load_source_into_temp(filename: str, table_name: str, session_id: str) -> str:
    """
    Load a source CSV into temp sandbox as a table for multi-step work or joins.
    """
    return load_source_into_temp(filename, table_name, session_id)

@mcp.tool()
def tool_query_temp(sql: str, session_id: str) -> str:
    """
    Run ANY SQL in the temp sandbox — CREATE, INSERT, UPDATE, JOIN freely.
    Nothing affects source data.
    """
    return query_temp(sql, session_id)

@mcp.tool()
def tool_list_temp_tables(session_id: str) -> str:
    """
    List all tables currently available in the temp sandbox session.
    """
    return list_temp_tables(session_id)

# ── Mount auth middleware and run ─────────────────────────────────────────────
app = mcp.streamable_http_app()
app.add_middleware(TokenAuthMiddleware)

if __name__ == "__main__":
    print("QData Agent MCP Server starting...")
    print(f"Endpoint     : http://0.0.0.0:8000/mcp")
    print(f"Health check : http://0.0.0.0:8000/health")
    print(f"Transport    : Streamable HTTP")
    uvicorn.run(app, host="0.0.0.0", port=8000)
