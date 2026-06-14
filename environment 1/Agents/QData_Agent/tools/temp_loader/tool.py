from core.duckdb_runner import load_into_temp
from core.redshift_runner import execute_on_redshift
from config import IS_PROD, TEMP_FOLDER
import duckdb
import pandas as pd

def load_source_into_temp(
    table_name: str,
    session_id: str,
    sql:        str,        # what to load — always required now
    username:   str = None,
    password:   str = None,
) -> str:
    """
    Dev:  loads result of sql (against CSV files) into temp table.
    Prod: loads result of sql (against Redshift) into temp table.
    sql example: 'SELECT * FROM sales' or 'SELECT * FROM sales JOIN customers ON ...'
    """
    try:
        if IS_PROD:
            df    = execute_on_redshift(sql, username, password)
            db_path  = TEMP_FOLDER / f"session_{session_id}.db"
            conn     = duckdb.connect(database=str(db_path))
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df")
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            conn.close()
        else:
            count = load_into_temp(session_id, table_name, sql)

        return f"Loaded → temp table '{table_name}' ({count:,} rows)."

    except Exception as e:
        return f"Error: {str(e)}"
