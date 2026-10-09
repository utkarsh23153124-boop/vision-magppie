"""Environment variable loader. Zero third-party dependencies."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    """
    Loads key-value pairs from a .env file into os.environ.
    - Does not override existing os.environ variables by default.
    - Ignores comments (#) and blank lines.
    - Strips surrounding quotes (' or ").
    """
    if path is None:
        path = ROOT / ".env"
    else:
        path = Path(path)

    if not path.is_file():
        return {}

    loaded = {}
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip surrounding matching quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        
        if key:
            loaded[key] = val
            if override or key not in os.environ:
                os.environ[key] = val

    return loaded
