import os
from pathlib import Path

# ── API Keys ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY")
LANGCHAIN_API_KEY= os.environ.get("LANGCHAIN_API_KEY")

os.environ["OPENAI_API_KEY"]       = OPENAI_API_KEY
os.environ["LANGCHAIN_API_KEY"]    = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"]    = "QData_Agent"
os.environ["LANGCHAIN_ENDPOINT"]   = "https://api.smith.langchain.com"

# ── Folders ───────────────────────────────────────────────────────────────────
SOURCE_FOLDER = Path("./data/source")
TEMP_FOLDER   = Path("./data/temp")
SOURCE_FOLDER.mkdir(parents=True, exist_ok=True)
TEMP_FOLDER.mkdir(parents=True, exist_ok=True)

# ── Agent settings ────────────────────────────────────────────────────────────
MAX_STEPS     = 8
TRUNCATE_OBS  = 1500
MAX_SQL_LEN   = 3000
MAX_TEMP_SQL  = 5000
MAX_DF_ROWS   = 50
