from pathlib import Path

def safe_path(folder: Path, filename: str) -> tuple[Path | None, str]:
    resolved = (folder / filename).resolve()
    if not str(resolved).startswith(str(folder.resolve())):
        return None, "Access denied: path traversal detected."
    if not resolved.exists():
        available = [f.name for f in folder.glob("*.csv")]
        return None, f"File '{filename}' not found. Available: {available}"
    return resolved, "ok"
