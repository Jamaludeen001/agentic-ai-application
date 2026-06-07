import duckdb
from core.pathguard import safe_path
from core.validators import validate_select_only
from core.duckdb_runner import execute_on_source, format_df
from config import SOURCE_FOLDER, MAX_SQL_LEN

def query_source(filename: str, sql: str) -> str:
    csv_path, err = safe_path(SOURCE_FOLDER, filename)
    if csv_path is None:
        return err
    if len(sql) > MAX_SQL_LEN:
        return f"Query too long (max {MAX_SQL_LEN} chars)."
    is_valid, reason = validate_select_only(sql)
    if not is_valid:
        return f"Query rejected: {reason}"
    try:
        return format_df(execute_on_source(csv_path, sql))
    except duckdb.Error as e:
        return f"DuckDB error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"
