import duckdb
from core.duckdb_runner import get_schema
from core.redshift_runner import get_redshift_schema
from core.pathguard import safe_path
from config import IS_PROD, SOURCE_FOLDER

def inspect_source_schema(
    filename: str = None,   # dev — csv filename
    username: str = None,   # prod — redshift username
    password: str = None,   # prod — redshift password
) -> str:
    try:
        if IS_PROD:
            return get_redshift_schema(username, password)
        else:
            csv_path, err = safe_path(SOURCE_FOLDER, filename)
            if csv_path is None:
                return err
            schema    = get_schema(str(csv_path))
            row_count = duckdb.execute(
                f"SELECT COUNT(*) FROM read_csv_auto('{csv_path}', header=True)"
            ).fetchone()[0]
            return f"File: {filename}\nRows: {row_count:,}\nColumns:\n{schema}"
    except Exception as e:
        return f"Error: {str(e)}"
