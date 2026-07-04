from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys


class Console:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.log_path.open("a", encoding="utf-8") as log:
            log.write(f"[{stamp}] {message}\n")

    def info(self, message: str) -> None:
        print(message)
        self._write_log(message)

    def error(self, message: str) -> None:
        print(f"ERROR: {message}", file=sys.stderr)
        self._write_log(f"ERROR: {message}")

    def header(self, title: str) -> None:
        line = "=" * 62
        self.info(f"\n{line}\n{title}\n{line}")

    def confirm(self, prompt: str, assume_yes: bool = False) -> bool:
        if assume_yes:
            self.info(f"{prompt} [auto-confirmed]")
            return True
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in {"y", "yes"}
