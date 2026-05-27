from __future__ import annotations

import os
from pathlib import Path
import sys


_ADD_OPENS = (
    "--add-opens=java.base/java.util=ALL-UNNAMED "
    "--add-opens=java.base/java.lang=ALL-UNNAMED "
    "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED "
    "--add-opens=java.base/java.io=ALL-UNNAMED"
)
_existing_java_opts = os.environ.get("JAVA_TOOL_OPTIONS", "")
if "add-opens" not in _existing_java_opts:
    os.environ["JAVA_TOOL_OPTIONS"] = (
        f"{_existing_java_opts} {_ADD_OPENS}".strip() if _existing_java_opts else _ADD_OPENS
    )


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gasprop.app import run_app


if __name__ == "__main__":
    run_app()
