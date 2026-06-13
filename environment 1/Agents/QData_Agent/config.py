import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Environment ───────────────────────────────────────────────────────────────
ENV     = os.environ.get("ENV", "dev")
IS_PROD = ENV == "prod"

# ── API Keys ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set.")

LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY")
if not LANGCHAIN_API_KEY:
    raise ValueError("LANGCHAIN_API_KEY is not set.")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

os.environ["OPENAI_API_KEY"]       = OPENAI_API_KEY
os.environ["LANGCHAIN_API_KEY"]    = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"]   = "https://api.smith.langchain.com"

LANGCHAIN_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "QData_Agent")
os.environ["LANGCHAIN_PROJECT"]    = LANGCHAIN_PROJECT

# ── Folders (dev) ─────────────────────────────────────────────────────────────
SOURCE_FOLDER = Path("./data/source")
TEMP_FOLDER   = Path("./data/temp")
SOURCE_FOLDER.mkdir(parents=True, exist_ok=True)
TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

# ── Redshift (prod) ───────────────────────────────────────────────────────────
REDSHIFT_HOST     = os.environ.get("REDSHIFT_HOST")
REDSHIFT_PORT     = int(os.environ.get("REDSHIFT_PORT", "5439"))
REDSHIFT_DATABASE = os.environ.get("REDSHIFT_DATABASE")

# ── JWT ───────────────────────────────────────────────────────────────────────
KMS_KEY_ID = os.environ.get("KMS_KEY_ID")    # prod
JWT_SECRET  = os.environ.get("JWT_SECRET")   # dev
ISSUER      = os.environ.get("ISSUER",    "qdataagent-client")
AUDIENCE    = os.environ.get("AUDIENCE",  "qdataagent-mcp-server")
ACCESS_TTL  = int(os.environ.get("ACCESS_TTL", "3600"))

# ── Validate based on environment ─────────────────────────────────────────────
if IS_PROD:
    if not REDSHIFT_HOST:
        raise ValueError("REDSHIFT_HOST is not set.")
    if not REDSHIFT_DATABASE:
        raise ValueError("REDSHIFT_DATABASE is not set.")
    if not KMS_KEY_ID:
        raise ValueError("KMS_KEY_ID is not set.")
else:
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise ValueError("JWT_SECRET is not set or too weak (min 32 chars).")

# ── Agent settings ────────────────────────────────────────────────────────────
MAX_STEPS    = 8
TRUNCATE_OBS = 1500
MAX_SQL_LEN  = 3000
MAX_TEMP_SQL = 5000
MAX_DF_ROWS  = 50
