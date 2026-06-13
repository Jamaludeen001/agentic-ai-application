import pandas as pd
from config import REDSHIFT_HOST, REDSHIFT_PORT, REDSHIFT_DATABASE

def get_redshift_connection(username: str, password: str):
    import redshift_connector
    return redshift_connector.connect(
        host     = REDSHIFT_HOST,
        database = REDSHIFT_DATABASE,
        port     = REDSHIFT_PORT,
        user     = username,
        password = password,
    )

def execute_on_redshift(sql: str, username: str, password: str) -> pd.DataFrame:
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
