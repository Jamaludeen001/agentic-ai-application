import redshift_connector
import pandas as pd
from config import TEMP_FOLDER
from functools import lru_cache

def get_redshift_connection(username: str, password: str):
    """
    Connect to Redshift as the actual user.
    Redshift enforces their table permissions directly.
    """
    return redshift_connector.connect(
        host     = "your-cluster.redshift.amazonaws.com",
        database = "your_database",
        port     = 5439,
        user     = username,
        password = password,
    )

def execute_on_redshift(sql: str, username: str, password: str) -> pd.DataFrame:
    """
    Execute query as the user — Redshift handles access control.
    If user has no access to a table, Redshift raises an error naturally.
    """
    conn   = get_redshift_connection(username, password)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=cols)
    finally:
        cursor.close()
        conn.close()

def get_redshift_schema(username: str, password: str) -> str:
    """
    Get all tables and schemas the user has access to.
    Redshift only returns what this user can see.
    """
    sql = """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name, ordinal_position
    """
    conn   = get_redshift_connection(username, password)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=cols).to_string(index=False)
    finally:
        cursor.close()
        conn.close()
