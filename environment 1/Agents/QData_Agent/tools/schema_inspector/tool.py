import duckdb
from core.duckdb_runner import get_schema, list_source_files
from core.redshift_runner import get_redshift_schema
from core.pathguard import safe_path
from config import IS_PROD, SOURCE_FOLDER

def inspect_source_schema(
    filename: str = None,
    username: str = None,
    password: str = None,
) -> str:
    try:
        if IS_PROD:
            return get_redshift_schema(username, password)
        else:
            if filename:
                # Single file schema
                csv_path, err = safe_path(SOURCE_FOLDER, filename)
                if csv_path is None:
                    return err
                table_name = csv_path.stem   # sales.csv → sales
                schema     = get_schema(str(csv_path))
                row_count  = duckdb.execute(
                    f"SELECT COUNT(*) FROM read_csv_auto('{csv_path}', header=True)"
                ).fetchone()[0]
                return (
                    f"File       : {filename}\n"
                    f"Table name : {table_name}\n"   # ← agent uses this in SQL
                    f"Rows       : {row_count:,}\n"
                    f"Columns    :\n{schema}"
                )
            else:
                # No filename — list all available files and their table names
                return f"Available source files:\n{list_source_files()}"
    except Exception as e:
        return f"Error: {str(e)}"
