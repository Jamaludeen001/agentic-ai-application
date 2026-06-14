import jwt
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from auth.jwt_handler import verify_service_token
from tools.schema_inspector.tool import inspect_source_schema
from tools.source_query.tool import query_source
from tools.temp_loader.tool import load_source_into_temp
from tools.temp_query.tool import query_temp
from tools.temp_inspector.tool import list_temp_tables
from config import IS_PROD

class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"error": "Missing token."})

        token = auth_header.split("Bearer ")[-1].strip()
        try:
            payload = verify_service_token(token)
            if payload.get("type") != "service":
                return JSONResponse(status_code=403, content={"error": "Not a service token."})
            request.state.user_id        = payload.get("sub")
            request.state.jwt_payload    = payload

        except jwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"error": "Token expired."})
        except jwt.InvalidTokenError as e:
            return JSONResponse(status_code=403, content={"error": f"Invalid token: {e}"})

        return await call_next(request)

mcp = FastMCP(name="QData_Agent", host="0.0.0.0", port=8000)

@mcp.tool()
def tool_inspect_source_schema(
    filename: str = None,
    username: str = None,
    password: str = None,
) -> str:
    """
    Inspect schema of a source file.
    Dev: pass filename (e.g. 'sales.csv') to get schema of that file.
         Leave filename empty to list all available files and their table names.
    Prod: pass username and password — returns all Redshift tables user can access.
    IMPORTANT: table name in SQL = filename without .csv extension.
               sales.csv → use 'sales' in SQL
               customers.csv → use 'customers' in SQL
    Always call this FIRST before writing any query.
    """
    return inspect_source_schema(filename=filename, username=username, password=password)

@mcp.tool()
def tool_query_source(
    sql:      str,
    username: str = None,
    password: str = None,
) -> str:
    """
    Run a READ-ONLY SELECT query on source data.
    Dev: table name = filename without .csv extension.
         sales.csv → SELECT * FROM sales
         customers.csv → SELECT * FROM customers
         join:  SELECT * FROM sales s JOIN customers c ON s.id = c.id
    Prod: standard Redshift SQL, table name as it exists in Redshift.
    Only SELECT/WITH/EXPLAIN allowed — no INSERT/UPDATE/DELETE/DROP.
    """
    return query_source(sql=sql, username=username, password=password)

@mcp.tool()
def tool_load_source_into_temp(
    table_name: str,
    session_id: str,
    sql:        str,
    username:   str = None,
    password:   str = None,
) -> str:
    """
    Load result of a source SQL query into temp sandbox as a named table.
    Use for multi-step transformations or when you need to build intermediate results.
    sql example: 'SELECT * FROM sales' loads full sales into temp as table_name.
    sql example: 'SELECT * FROM sales JOIN customers ON sales.id = customers.id'
    After loading use tool_query_temp to work with it freely.
    """
    return load_source_into_temp(
        table_name=table_name,
        session_id=session_id,
        sql=sql,
        username=username,
        password=password,
    )

@mcp.tool()
def tool_query_temp(sql: str, session_id: str) -> str:
    """
    Run ANY SQL in the temp sandbox — CREATE, INSERT, UPDATE, JOIN freely.
    Nothing affects source data. Same for both dev and prod.
    """
    return query_temp(sql=sql, session_id=session_id)

@mcp.tool()
def tool_list_temp_tables(session_id: str) -> str:
    """
    List all tables in the temp sandbox session.
    Same for both dev and prod.
    """
    return list_temp_tables(session_id=session_id)

app = mcp.streamable_http_app()
app.add_middleware(JWTAuthMiddleware)

if __name__ == "__main__":
    print("QData Agent MCP Server starting...")
    print(f"Endpoint     : http://0.0.0.0:8000/mcp")
    print(f"Health check : http://0.0.0.0:8000/health")
    print(f"Transport    : Streamable HTTP")
    print(f"Auth         : JWT ({'KMS RS256' if IS_PROD else 'Local HS256'})")
    print(f"Data source  : {'Redshift' if IS_PROD else 'CSV (DuckDB)'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
