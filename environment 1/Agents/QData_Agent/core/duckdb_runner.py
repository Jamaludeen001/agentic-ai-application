import duckdb
import pandas as pd
from pathlib import Path
from functools import lru_cache
from config import TEMP_FOLDER, MAX_DF_ROWS

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

def execute_on_source(csv_path: Path, sql: str) -> pd.DataFrame:
    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute(
            f"CREATE VIEW data AS SELECT * FROM read_csv_auto('{csv_path}', header=True)"
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

def cleanup_session(session_id: str):
    db_path = TEMP_FOLDER / f"session_{session_id}.db"
    if db_path.exists():
        db_path.unlink()
