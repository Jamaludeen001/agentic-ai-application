import sqlglot
import sqlglot.expressions as exp
from config import SOURCE_FOLDER

MUTATION_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop,
    exp.Alter, exp.Merge, exp.Transaction,
    exp.Commit, exp.Rollback, exp.Grant, exp.Revoke, exp.Command,
)

def _parse_ast(sql: str) -> tuple[bool, str, list]:
    try:
        statements = sqlglot.parse(sql, dialect="duckdb")
        if not statements:
            return False, "Empty query.", []
        return True, "ok", statements
    except sqlglot.errors.ParseError as e:
        return False, f"Invalid SQL syntax: {str(e)}", []

def _has_mutation(statements: list) -> tuple[bool, str]:
    for statement in statements:
        if statement is None:
            continue
        for node in statement.walk():
            if isinstance(node, MUTATION_NODES):
                return True, type(node).__name__
            
        # fallback keyword check for unsupported statements
        sql_text = statement.sql().lower()
        if "truncate" in sql_text:
            return True, "Truncate"
    return False, ""

def validate_select_only(sql: str) -> tuple[bool, str]:
    ok, err, statements = _parse_ast(sql)
    if not ok:
        return False, err
    for statement in statements:
        if statement is None:
            continue
        if not isinstance(statement, (exp.Select, exp.With)):
            return False, f"Only SELECT allowed on source data. Got: {type(statement).__name__}"
    mutated, node_name = _has_mutation(statements)
    if mutated:
        return False, f"Blocked: '{node_name}' not allowed on source data."
    return True, "ok"

def validate_temp_sql(sql: str) -> tuple[bool, str]:
    ok, err, _ = _parse_ast(sql)
    if not ok:
        return False, err
    if str(SOURCE_FOLDER).lower() in sql.lower():
        return False, "Cannot reference source folder path in temp queries."
    return True, "ok"
