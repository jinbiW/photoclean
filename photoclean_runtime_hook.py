import os
import sys
from pathlib import Path


log_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PhotoClean" / "logs"
log_root.mkdir(parents=True, exist_ok=True)
stream = (log_root / "photoclean.log").open("a", encoding="utf-8", buffering=1)
sys.stdout = stream
sys.stderr = stream
