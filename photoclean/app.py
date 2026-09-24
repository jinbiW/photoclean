from __future__ import annotations

import sys
import os
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication

_LOG_STREAM = None


def ensure_output_streams(log_file: Path | None = None):
    """Give GUI-only pythonw processes streams required by Torch and LPIPS."""
    global _LOG_STREAM
    if (
        not getattr(sys, "frozen", False)
        and sys.stdout is not None
        and sys.stderr is not None
    ):
        return None
    if log_file is None:
        log_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PhotoClean" / "logs"
        log_file = log_root / "photoclean.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    _LOG_STREAM = log_file.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _LOG_STREAM
    if sys.stderr is None:
        sys.stderr = _LOG_STREAM
    return _LOG_STREAM


def main() -> int:
    ensure_output_streams()
    if "--self-test-models" in sys.argv:
        from .scanner import PhotoScanner

        try:
            PhotoScanner()._load_models()
            return 0
        except Exception:
            traceback.print_exc()
            return 1
    from .ui import MainWindow

    application = QApplication(sys.argv)
    application.setApplicationName("PhotoClean")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
