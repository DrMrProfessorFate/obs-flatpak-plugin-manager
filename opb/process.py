from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Sequence

from opb.console import Console


class CommandError(RuntimeError):
    pass


class ProcessRunner:
    def __init__(self, console: Console):
        self.console = console

    def run(
        self,
        command: Sequence[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        printable = " ".join(command)
        self.console.info(f"\n$ {printable}\n")

        process = subprocess.Popen(
            list(command),
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        output: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            self.console._write_log(line.rstrip("\n"))
            output.append(line)

        code = process.wait()
        result = subprocess.CompletedProcess(list(command), code, "".join(output), "")

        if check and code != 0:
            raise CommandError(f"Command failed with exit code {code}: {printable}")

        return result
