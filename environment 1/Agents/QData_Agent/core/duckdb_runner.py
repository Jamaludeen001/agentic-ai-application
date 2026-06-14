import duckdb
import pandas as pd
from pathlib import Path
from functools import lru_cache
from config import TEMP_FOLDER, SOURCE_FOLDER, MAX_DF_ROWS

def format_df(df: pd.DataFrame) -> str:
    if df.empty:
        return "Query returned no rows."
    truncated = len(df) > MAX_DF_ROWS
    return (
        f"Rows: {len(df)}{' (showing first 50)' if truncated else ''}\n\n"
        + df.head(MAX_DF_ROWS).to_string(index=False)
    )

@lru_cache(maxsize=32)
def get_schema(csv_path: str) -> str:
    conn = duckdb.connect(database=":memory:")
    try:
        df = conn.execute(
            f"DESCRIBE SELECT * FROM read_csv_auto('{csv_path}', header=True)"
        ).fetchdf()
        return "\n".join(
            f"  {row['column_name']} ({row['column_type']})"
            for _, row in df.iterrows()
        )
    finally:
        conn.close()

def execute_on_source(sql: str) -> pd.DataFrame:
    """
    Execute SQL directly against CSV files in SOURCE_FOLDER.
    Table name in SQL = filename without .csv extension.
    e.g. sales.csv → SELECT * FROM sales
         customers.csv → SELECT * FROM customers
    DuckDB reads the files directly — no view creation needed.
    """
    conn = duckdb.connect(database=":memory:")
    try:
        # Register ALL csv files in source folder as views automatically
        # so any table name used in SQL resolves to the right file
        for csv_file in SOURCE_FOLDER.glob("*.csv"):
            table_name = csv_file.stem   # sales.csv → sales
            conn.execute(
                f"CREATE VIEW {table_name} AS "
                f"SELECT * FROM read_csv_auto('{csv_file}', header=True)"
            )
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()

def execute_on_temp(sql: str, session_id: str) -> pd.DataFrame:
    db_path = TEMP_FOLDER / f"session_{session_id}.db"
    conn    = duckdb.connect(database=str(db_path))
    try:
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()

def load_into_temp(session_id: str, table_name: str, sql: str) -> int:
    """
    Load result of a source query into temp DuckDB sandbox.
    Source files registered automatically so SQL can reference any of them.
    """
    source_conn = duckdb.connect(database=":memory:")
    try:
        # Register all source files
        for csv_file in SOURCE_FOLDER.glob("*.csv"):
            source_conn.execute(
                f"CREATE VIEW {csv_file.stem} AS "
                f"SELECT * FROM read_csv_auto('{csv_file}', header=True)"
            )
        df = source_conn.execute(sql).fetchdf()
    finally:
        source_conn.close()

    # Write into temp session
    db_path  = TEMP_FOLDER / f"session_{session_id}.db"
    temp_conn= duckdb.connect(database=str(db_path))
    try:
        temp_conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df"
        )
        count = temp_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        return count
    finally:
        temp_conn.close()

def list_source_files() -> str:
    """List all available CSV files in source folder."""
    files = [f.name for f in SOURCE_FOLDER.glob("*.csv")]
    if not files:
        return "No CSV files found in source folder."
    return "\n".join(f"  - {f} → table name: {Path(f).stem}" for f in files)

def cleanup_session(session_id: str):
    db_path = TEMP_FOLDER / f"session_{session_id}.db"
    if db_path.exists():
        db_path.unlink()
