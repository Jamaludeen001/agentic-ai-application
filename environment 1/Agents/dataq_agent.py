import os
import json
import uuid
import logging
import duckdb
import sqlglot
import sqlglot.expressions as exp
import pandas as pd
import json_repair
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, List, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langsmith import Client
from langsmith.run_helpers import traceable

# ── Logging (replaces all verbose print statements) ───────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
os.environ["OPENAI_API_KEY"]       = "your-openai-api-key"
os.environ["LANGCHAIN_API_KEY"]    = "your-langsmith-api-key"
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"]    = "custom-agent-production"
os.environ["LANGCHAIN_ENDPOINT"]   = "https://api.smith.langchain.com"

SOURCE_FOLDER = Path("./data/source")
TEMP_FOLDER   = Path("./data/temp")
SOURCE_FOLDER.mkdir(parents=True, exist_ok=True)
TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

smith = Client()

# ── SQL AST Validator ─────────────────────────────────────────────────────────
MUTATION_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop,
    exp.Alter,  exp.Truncate, exp.Merge, exp.Transaction,
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
    return False, ""

def validate_select_only(sql: str) -> tuple[bool, str]:
    ok, err, statements = _parse_ast(sql)
    if not ok:
        return False, err
    for statement in statements:
        if statement is None:
            continue
        if not isinstance(statement, (exp.Select, exp.With, exp.Explain)):
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

# ── Path Guard ────────────────────────────────────────────────────────────────
def _safe_path(folder: Path, filename: str) -> tuple[Path | None, str]:
    resolved = (folder / filename).resolve()
    if not str(resolved).startswith(str(folder.resolve())):
        return None, "Access denied: path traversal detected."
    if not resolved.exists():
        available = [f.name for f in folder.glob("*.csv")]
        return None, f"File '{filename}' not found. Available: {available}"
    return resolved, "ok"

# ── DuckDB Execution ──────────────────────────────────────────────────────────
@lru_cache(maxsize=32)
def _get_schema(csv_path: str) -> str:
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

def _execute_on_source(csv_path: Path, sql: str) -> pd.DataFrame:
    conn = duckdb.connect(database=":memory:")
    try:
        conn.execute(
            f"CREATE VIEW data AS SELECT * FROM read_csv_auto('{csv_path}', header=True)"
        )
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()

def _execute_on_temp(sql: str, session_id: str) -> pd.DataFrame:
    db_path = TEMP_FOLDER / f"session_{session_id}.db"
    conn    = duckdb.connect(database=str(db_path))
    try:
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()

def _format_df(df: pd.DataFrame) -> str:
    if df.empty:
        return "Query returned no rows."
    truncated = len(df) > 50
    return (
        f"Rows: {len(df)}{' (showing first 50)' if truncated else ''}\n\n"
        + df.head(50).to_string(index=False)
    )

def cleanup_temp_session(session_id: str):
    db_path = TEMP_FOLDER / f"session_{session_id}.db"
    if db_path.exists():
        db_path.unlink()
        logger.info("Cleaned up temp session: %s", session_id)

# ── Tool Implementations (pure functions — no @tool decorator needed) ─────────
def _inspect_source_schema(filename: str) -> str:
    csv_path, err = _safe_path(SOURCE_FOLDER, filename)
    if csv_path is None:
        return err
    try:
        schema    = _get_schema(str(csv_path))
        row_count = duckdb.execute(
            f"SELECT COUNT(*) FROM read_csv_auto('{csv_path}', header=True)"
        ).fetchone()[0]
        return f"File: {filename}\nRows: {row_count:,}\nColumns:\n{schema}"
    except Exception as e:
        return f"Error: {str(e)}"

def _query_source(filename: str, sql: str) -> str:
    csv_path, err = _safe_path(SOURCE_FOLDER, filename)
    if csv_path is None:
        return err
    if len(sql) > 3000:
        return "Query too long (max 3000 chars)."
    is_valid, reason = validate_select_only(sql)
    if not is_valid:
        return f"Query rejected: {reason}"
    try:
        return _format_df(_execute_on_source(csv_path, sql))
    except duckdb.Error as e:
        return f"DuckDB error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

def _load_source_into_temp(filename: str, table_name: str, session_id: str) -> str:
    csv_path, err = _safe_path(SOURCE_FOLDER, filename)
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

def _query_temp(sql: str, session_id: str) -> str:
    if len(sql) > 5000:
        return "Query too long (max 5000 chars)."
    is_valid, reason = validate_temp_sql(sql)
    if not is_valid:
        return f"Query rejected: {reason}"
    try:
        return _format_df(_execute_on_temp(sql, session_id))
    except duckdb.Error as e:
        return f"DuckDB error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

def _list_temp_tables(session_id: str) -> str:
    try:
        return _format_df(
            _execute_on_temp("SELECT table_name FROM duckdb_tables()", session_id)
        )
    except Exception as e:
        return f"Error: {str(e)}"

# ── Tool Registry ─────────────────────────────────────────────────────────────
# Tools are plain functions — agent calls them directly, LLM never sees internals
def make_tools(session_id: str) -> Dict[str, Dict]:
    return {
        "inspect_source_schema": {
            "call":        lambda args: _inspect_source_schema(args["filename"]),
            "description": "Inspect column names and data types of a source CSV file. Always call this FIRST before writing any query. Input: {\"filename\": \"sales.csv\"}",
        },
        "query_source": {
            "call":        lambda args: _query_source(args["filename"], args["sql"]),
            "description": "Run a READ-ONLY SELECT query on source CSV. Table always named 'data'. Only SELECT/WITH/EXPLAIN allowed. Input: {\"filename\": \"sales.csv\", \"sql\": \"SELECT ...\"}",
        },
        "load_source_into_temp": {
            "call":        lambda args: _load_source_into_temp(args["filename"], args["table_name"], session_id),
            "description": "Load a source CSV into the temp sandbox as a table for multi-step work. Input: {\"filename\": \"sales.csv\", \"table_name\": \"sales\"}",
        },
        "query_temp": {
            "call":        lambda args: _query_temp(args["sql"], session_id),
            "description": "Run ANY SQL in the temp sandbox — CREATE, INSERT, UPDATE, JOIN freely. Nothing affects source data. Input: {\"sql\": \"SELECT ...\"}",
        },
        "list_temp_tables": {
            "call":        lambda args: _list_temp_tables(session_id),
            "description": "List all tables currently in the temp sandbox session. Input: {}",
        },
    }

# ── System Prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(tools: Dict) -> str:
    tool_docs = "\n".join(
        f"- {name}: {meta['description']}"
        for name, meta in tools.items()
    )
    return f"""You are a data analyst assistant that solves tasks step by step.

Available tools:
{tool_docs}

Rules:
- ALWAYS respond with a SINGLE JSON object and NOTHING ELSE.
- To use a tool:
  {{"type": "action", "tool": "<tool_name>", "input": {{<tool specific input dict>}}}}
- To give final answer:
  {{"type": "final", "answer": "<your answer>"}}
- No markdown, no code fences — pure JSON only.
- For CSV tasks: always call inspect_source_schema first, then query_source for simple reads,
  or load_source_into_temp + query_temp for multi-step work or joins.
- Use tools only when necessary."""

# ── JSON Parser ───────────────────────────────────────────────────────────────
def parse_json(raw: str) -> Dict[str, Any]:
    result = json_repair.repair_json(raw, return_objects=True)
    if isinstance(result, dict):
        return result
    raise ValueError(f"Could not parse into dict: {raw[:200]}")

# ── LangSmith Audit Logger ────────────────────────────────────────────────────
class LangSmithAudit:
    def __init__(self, session_id: str, project: str = "custom-agent-production"):
        self.session_id = session_id
        self.project    = project

    def log_run(
        self,
        user_query:   str,
        final_answer: str,
        steps:        List[Tuple[str, str, str]],
        terminated:   str,
        run_id:       str,
    ):
        """Log the full agent run to LangSmith for audit."""
        try:
            smith.create_run(
                id          = run_id,
                name        = "custom-agent-turn",
                run_type    = "chain",
                project_name= self.project,
                inputs      = {"user_query": user_query, "session_id": self.session_id},
                outputs     = {"final_answer": final_answer, "terminated": terminated},
                extra       = {
                    "metadata": {
                        "session_id":  self.session_id,
                        "steps_count": len(steps),
                        "tools_used":  [s[0] for s in steps],
                        "terminated":  terminated,
                    }
                },
            )
            # Log each tool call as a child run for full traceability
            for i, (tool_name, tool_input, observation) in enumerate(steps):
                smith.create_run(
                    name         = f"tool-{tool_name}",
                    run_type     = "tool",
                    project_name = self.project,
                    parent_run_id= run_id,
                    inputs       = {"tool": tool_name, "input": tool_input},
                    outputs      = {"observation": observation[:500]},
                    extra        = {"metadata": {"step": i + 1, "session_id": self.session_id}},
                )
        except Exception as e:
            logger.warning("LangSmith audit log failed: %s", e)

    def log_feedback(self, run_id: str, score: float, comment: str = ""):
        try:
            smith.create_feedback(
                run_id  = run_id,
                key     = "user-feedback",
                score   = score,
                comment = comment,
            )
        except Exception as e:
            logger.warning("LangSmith feedback log failed: %s", e)

# ── Fully Custom Agent ────────────────────────────────────────────────────────
class FullyCustomAgent:
    def __init__(
        self,
        llm,
        session_id:   str,
        max_steps:    int  = 8,
        truncate_obs: int  = 1500,
    ):
        self.llm          = llm
        self.session_id   = session_id
        self.max_steps    = max_steps
        self.truncate_obs = truncate_obs
        self.tools        = make_tools(session_id)
        self.system_prompt= build_system_prompt(self.tools)
        self.audit        = LangSmithAudit(session_id)

    def _call_llm(self, messages: list) -> str:
        out = self.llm.invoke(messages)
        if hasattr(out, "content"):
            return out.content
        if isinstance(out, dict) and "content" in out:
            return out["content"]
        return str(out)

    def _build_messages(self, user_query: str, history: list, steps: List) -> list:
        scratchpad = ""
        for i, (act, inp, obs) in enumerate(steps, 1):
            scratchpad += (
                f"\nStep {i}\n"
                f"Action: {act}\n"
                f"Input: {inp}\n"
                f"Observation: {obs}\n"
            )

        messages = [{"role": "system", "content": self.system_prompt}]
        for h in history:
            messages.append(h)
        messages.append({"role": "user", "content": user_query})
        if scratchpad:
            messages.append({"role": "assistant", "content": f"Scratchpad:{scratchpad}"})
        return messages

    def run(
        self,
        user_query: str,
        history:    List[Dict] = [],
    ) -> Dict[str, Any]:

        steps:     List[Tuple[str, str, str]] = []
        run_id   = str(uuid.uuid4())

        for step_idx in range(1, self.max_steps + 1):
            messages = self._build_messages(user_query, history, steps)
            raw      = self._call_llm(messages)
            logger.debug("Step %d raw output: %s", step_idx, raw)

            # ── Parse JSON ────────────────────────────────────────────────────
            try:
                obj = parse_json(raw)
            except Exception as e:
                logger.warning("JSON parse failed at step %d: %s", step_idx, e)
                steps.append(("parse_error", raw[:100], f"JSON parse error: {e}"))
                continue

            typ = obj.get("type")

            # ── Final answer ──────────────────────────────────────────────────
            if typ == "final":
                answer = obj.get("answer", "").strip()
                self.audit.log_run(user_query, answer, steps, "final_answer", run_id)
                return {
                    "final_answer": answer,
                    "steps":        steps,
                    "terminated":   "final_answer",
                    "run_id":       run_id,
                }

            # ── Tool action ───────────────────────────────────────────────────
            if typ == "action":
                tool_name  = obj.get("tool", "")
                tool_input = obj.get("input", {})

                # Ensure input is always dict
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except Exception:
                        tool_input = {"input": tool_input}

                # Invalid tool → inject as observation, LLM self-corrects
                if tool_name not in self.tools:
                    steps.append((
                        tool_name, str(tool_input),
                        f"Invalid tool '{tool_name}'. Available: {list(self.tools.keys())}"
                    ))
                    continue

                # Execute tool
                try:
                    observation = str(self.tools[tool_name]["call"](tool_input))
                except Exception as e:
                    observation = f"ToolError: {type(e).__name__}: {e}"

                if len(observation) > self.truncate_obs:
                    observation = observation[:self.truncate_obs] + " ... [truncated]"

                steps.append((tool_name, str(tool_input), observation))
                continue

            # ── Unknown type → inject as observation, keep loop alive ─────────
            steps.append((
                "unknown_type", str(obj),
                "Unknown response type. Respond with 'action' or 'final' only."
            ))
            continue

        # ── Max steps reached ─────────────────────────────────────────────────
        logger.warning("Max steps reached for query: %s", user_query)
        messages = self._build_messages(user_query, history, steps)
        messages.append({
            "role":    "user",
            "content": "Max steps reached. Give your best final answer now as JSON: {\"type\":\"final\",\"answer\":\"...\"}"
        })
        raw = self._call_llm(messages)
        try:
            obj = parse_json(raw)
            ans = obj.get("answer", "Max steps reached.")
        except Exception:
            ans = "Max steps reached. Could not produce final answer."

        self.audit.log_run(user_query, ans, steps, "max_steps", run_id)
        return {"final_answer": ans, "steps": steps, "terminated": "max_steps", "run_id": run_id}


# ── Intent Classifier ─────────────────────────────────────────────────────────
def classify_intent(message: str, llm) -> str:
    messages = [
        {"role": "system", "content": """Classify the user message into exactly one of:
- POSITIVE_FEEDBACK
- NEGATIVE_FEEDBACK
- CONTINUATION
Reply with ONLY the label."""},
        {"role": "user", "content": message},
    ]
    out = llm.invoke(messages)
    intent = out.content.strip() if hasattr(out, "content") else str(out).strip()
    if intent not in ("POSITIVE_FEEDBACK", "NEGATIVE_FEEDBACK", "CONTINUATION"):
        return "CONTINUATION"
    return intent


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    session_id     = str(uuid.uuid4())
    history        = []
    last_run_id    = None

    llm            = ChatOpenAI(model="gpt-4o",      temperature=0,  max_tokens=2000)
    classifier_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,  max_tokens=20)

    agent  = FullyCustomAgent(llm=llm, session_id=session_id)
    audit  = LangSmithAudit(session_id=session_id)

    print(f"Session : {session_id}")
    print(f"Source  : {SOURCE_FOLDER.resolve()}")
    print("Drop CSV files in ./data/source/ and start asking.\n")

    try:
        while True:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "exit":
                break

            intent = classify_intent(user_input, classifier_llm)

            if intent == "POSITIVE_FEEDBACK" and last_run_id:
                audit.log_feedback(last_run_id, score=1.0, comment=user_input)
                print("Bot: Glad that helped! Anything else?\n")
                continue

            if intent == "NEGATIVE_FEEDBACK" and last_run_id:
                audit.log_feedback(last_run_id, score=0.0, comment=user_input)
                print("Bot: Sorry about that! What were you looking for exactly?\n")
                continue

            result      = agent.run(user_input, history)
            last_run_id = result["run_id"]

            # Update conversation history
            history.append({"role": "user",      "content": user_input})
            history.append({"role": "assistant",  "content": result["final_answer"]})

            print(f"Bot: {result['final_answer']}\n")

    finally:
        cleanup_temp_session(session_id)
        print("Session cleaned up.")
