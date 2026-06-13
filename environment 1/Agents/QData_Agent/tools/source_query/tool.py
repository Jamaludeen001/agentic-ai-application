from core.validators import validate_select_only
from core.duckdb_runner import execute_on_source, format_df
from core.redshift_runner import execute_on_redshift
from core.pathguard import safe_path
from config import IS_PROD, SOURCE_FOLDER, MAX_SQL_LEN

def query_source(
    sql:      str,
    filename: str = None,   # dev — csv filename
    username: str = None,   # prod — redshift username
    password: str = None,   # prod — redshift password
) -> str:
    if len(sql) > MAX_SQL_LEN:
        return f"Query too long (max {MAX_SQL_LEN} chars)."

    is_valid, reason = validate_select_only(sql)
    if not is_valid:
        return f"Query rejected: {reason}"

    try:
        if IS_PROD:
            df = execute_on_redshift(sql, username, password)
        else:
            csv_path, err = safe_path(SOURCE_FOLDER, filename)
            if csv_path is None:
                return err
            df = execute_on_source(csv_path, sql)

        return format_df(df)

    except Exception as e:
        return f"Error: {str(e)}"
