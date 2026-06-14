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
