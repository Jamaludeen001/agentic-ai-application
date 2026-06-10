import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env file ────────────────────────────────────────────────────────────
load_dotenv()

# ── API Keys — validate on startup, fail fast if missing ─────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set. Check your .env file.")

LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY")
if not LANGCHAIN_API_KEY:
    raise ValueError("LANGCHAIN_API_KEY is not set. Check your .env file.")

MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")
if not MCP_AUTH_TOKEN:
    raise ValueError("MCP_AUTH_TOKEN is not set. Check your .env file.")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

# ── Set LangSmith env vars ────────────────────────────────────────────────────
os.environ["OPENAI_API_KEY"]       = OPENAI_API_KEY
os.environ["LANGCHAIN_API_KEY"]    = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"]   = "https://api.smith.langchain.com"

LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "QData_Agent")
os.environ["LANGCHAIN_PROJECT"]    = LANGCHAIN_PROJECT

# ── Folders ───────────────────────────────────────────────────────────────────
SOURCE_FOLDER = Path("./data/source")
TEMP_FOLDER   = Path("./data/temp")
SOURCE_FOLDER.mkdir(parents=True, exist_ok=True)
TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

# ── Agent settings ────────────────────────────────────────────────────────────
MAX_STEPS    = 8
TRUNCATE_OBS = 1500
MAX_SQL_LEN  = 3000
MAX_TEMP_SQL = 5000
MAX_DF_ROWS  = 50
