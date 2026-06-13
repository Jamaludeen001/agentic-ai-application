from core.duckdb_runner import execute_on_temp, format_df
from core.validators import validate_temp_sql
from config import MAX_TEMP_SQL

def query_temp(sql: str, session_id: str) -> str:
    if len(sql) > MAX_TEMP_SQL:
        return f"Query too long (max {MAX_TEMP_SQL} chars)."

    is_valid, reason = validate_temp_sql(sql)
    if not is_valid:
        return f"Query rejected: {reason}"

    try:
        return format_df(execute_on_temp(sql, session_id))
    except Exception as e:
        return f"Error: {str(e)}"
