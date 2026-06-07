import duckdb
from core.pathguard import safe_path
from core.duckdb_runner import get_schema
from config import SOURCE_FOLDER

def inspect_source_schema(filename: str) -> str:
    csv_path, err = safe_path(SOURCE_FOLDER, filename)
    if csv_path is None:
        return err
    try:
        schema    = get_schema(str(csv_path))
        row_count = duckdb.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{csv_path}', header=True)"
        ).fetchone()[0]
        return f"File: {filename}\nRows: {row_count:,}\nColumns:\n{schema}"
    except Exception as e:
        return f"Error: {str(e)}"
