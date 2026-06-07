import duckdb
from core.pathguard import safe_path
from config import SOURCE_FOLDER, TEMP_FOLDER

def load_source_into_temp(filename: str, table_name: str, session_id: str) -> str:
    csv_path, err = safe_path(SOURCE_FOLDER, filename)
    if csv_path is None:
        return err
    try:
        db_path = TEMP_FOLDER / f"session_{session_id}.db"
        conn    = duckdb.connect(database=str(db_path))
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} AS
            SELECT * FROM read_csv_auto('{csv_path}', header=True)
        """)
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        conn.close()
        return f"Loaded '{filename}' → temp table '{table_name}' ({count:,} rows)."
    except Exception as e:
        return f"Error: {str(e)}"
