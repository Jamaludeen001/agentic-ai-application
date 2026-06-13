import duckdb
from core.duckdb_runner import execute_on_source
from core.redshift_runner import execute_on_redshift
from core.pathguard import safe_path
from config import IS_PROD, SOURCE_FOLDER, TEMP_FOLDER

def load_source_into_temp(
    table_name: str,
    session_id: str,
    filename:   str = None,
    username:   str = None,
    password:   str = None,
    sql:        str = None,
) -> str:
    try:
        if IS_PROD:
            load_sql = sql or f"SELECT * FROM {table_name}"
            df       = execute_on_redshift(load_sql, username, password)
        else:
            csv_path, err = safe_path(SOURCE_FOLDER, filename)
            if csv_path is None:
                return err
            df = execute_on_source(csv_path, "SELECT * FROM data")

        db_path = TEMP_FOLDER / f"session_{session_id}.db"
        conn    = duckdb.connect(database=str(db_path))
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df"
        )
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        conn.close()
        return f"Loaded → temp table '{table_name}' ({count:,} rows)."

    except Exception as e:
        return f"Error: {str(e)}"
