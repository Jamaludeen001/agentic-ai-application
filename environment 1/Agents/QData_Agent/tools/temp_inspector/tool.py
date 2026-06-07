from core.duckdb_runner import execute_on_temp, format_df

def list_temp_tables(session_id: str) -> str:
    try:
        return format_df(
            execute_on_temp("SELECT table_name FROM duckdb_tables()", session_id)
        )
    except Exception as e:
        return f"Error: {str(e)}"
