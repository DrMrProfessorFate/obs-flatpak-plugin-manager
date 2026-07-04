from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from opb.console import Console
from opb.process import ProcessRunner


OBS_APP_ID = "com.obsproject.Studio"
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"


@dataclass(frozen=True)
class OBSInstall:
    scope: str
    version: str | None
    runtime: str
    sdk_branch: str


class FlatpakManager:
    def __init__(self, runner: ProcessRunner, console: Console):
        self.runner = runner
        self.console = console

    @staticmethod
    def host_tools_present() -> list[str]:
        missing = []
        for command in ("flatpak", "flatpak-builder", "git", "python3"):
            if shutil.which(command) is None:
                missing.append(command)
        return missing

    def ensure_user_flathub(self) -> None:
        self.runner.run(
            [
                "flatpak", "--user", "remote-add", "--if-not-exists",
                "flathub", FLATHUB_REPO,
            ]
        )

    def detect_user_obs(self) -> OBSInstall | None:
        info = self._info("user", OBS_APP_ID)
        if info is None:
            return None
        return self._obs_from_info("user", info)

    def ensure_user_obs(self, assume_yes: bool = False) -> OBSInstall:
        existing = self.detect_user_obs()
        if existing:
            return existing

        if not self.console.confirm(
            "User-scoped Flatpak OBS is required. Install it from Flathub?",
            assume_yes,
        ):
            raise RuntimeError("OBS installation cancelled")

        self.runner.run(
            ["flatpak", "install", "--user", "-y", "flathub", OBS_APP_ID]
        )
        installed = self.detect_user_obs()
        if installed is None:
            raise RuntimeError("Flatpak reported success, but user-scoped OBS could not be detected")
        return installed

    def extension_is_installed(self, extension_id: str) -> bool:
        return self._info("user", extension_id) is not None

    def extension_location(self, extension_id: str) -> Path | None:
        result = subprocess.run(
            ["flatpak", "info", "--user", "--show-location", extension_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return Path(value) if value else None

    def extension_obs_modules(self, extension_id: str) -> list[Path]:
        location = self.extension_location(extension_id)
        if location is None:
            return []
        modules_dir = location / "files" / "lib" / "obs-plugins"
        if not modules_dir.is_dir():
            return []
        return sorted(path for path in modules_dir.glob("*.so") if path.is_file())

    def install_official_extension(self, extension_id: str) -> None:
        self.runner.run(
            ["flatpak", "install", "--user", "-y", "flathub", extension_id]
        )

    def uninstall_extension(self, extension_id: str) -> None:
        self.runner.run(
            ["flatpak", "uninstall", "--user", "-y", extension_id]
        )

    def ensure_sdk(self, sdk_branch: str) -> None:
        self.runner.run(
            [
                "flatpak", "install", "--user", "-y", "flathub",
                f"org.freedesktop.Sdk//{sdk_branch}",
            ]
        )

    def _info(self, scope: str, app_id: str) -> str | None:
        result = subprocess.run(
            ["flatpak", "info", f"--{scope}", app_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _obs_from_info(self, scope: str, info: str) -> OBSInstall:
        # Flatpak exposes the installed app version through `flatpak list`.
        version = self._installed_app_version(scope, OBS_APP_ID)
        runtime = self._show(scope, "--show-runtime", OBS_APP_ID)
        if not runtime:
            raise RuntimeError("Could not determine the OBS Flatpak runtime")
        parts = runtime.split("/")
        sdk_branch = parts[-1]
        if not sdk_branch:
            raise RuntimeError("Could not determine the matching Freedesktop SDK branch")
        return OBSInstall(scope=scope, version=version, runtime=runtime, sdk_branch=sdk_branch)

    def _installed_app_version(self, scope: str, app_id: str) -> str | None:
        result = subprocess.run(
            [
                "flatpak", "list", f"--{scope}", "--app",
                "--columns=application,version",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            application, separator, version = line.partition("\t")
            if not separator:
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                application, version = parts
            if application == app_id:
                version = version.strip()
                return version or None
        return None

    def _show(self, scope: str, option: str, app_id: str) -> str | None:
        result = subprocess.run(
            ["flatpak", "info", f"--{scope}", option, app_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None
