from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


OBS_PLUGIN_PREFIX = "com.obsproject.Studio.Plugin."


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    kind: str
    flatpak_id: str
    description: str
    source: str | None = None
    repository: str | None = None
    tag: str | None = None
    expected_commit: str | None = None
    source_dir: str | None = None
    module_name: str | None = None
    required_obs_major: int | None = None
    cmake_options: tuple[str, ...] = ()

    @property
    def extension_subdir(self) -> str:
        """The directory Flatpak derives from the extension ID suffix."""
        if not self.flatpak_id.startswith(OBS_PLUGIN_PREFIX):
            raise ValueError(
                f"Local plugin ID must begin with {OBS_PLUGIN_PREFIX}: {self.flatpak_id}"
            )
        suffix = self.flatpak_id.removeprefix(OBS_PLUGIN_PREFIX)
        if not suffix or "/" in suffix or "\\" in suffix:
            raise ValueError(f"Invalid OBS extension ID suffix: {self.flatpak_id}")
        return suffix


class Registry:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[Plugin]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        entries = raw.get("plugins")
        if not isinstance(entries, list):
            raise ValueError("registry/plugins.json must contain a 'plugins' list")

        plugins: list[Plugin] = []
        seen: set[str] = set()
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Each plugin entry must be an object")
            plugin = self._parse(item)
            if plugin.id in seen:
                raise ValueError(f"Duplicate plugin id: {plugin.id}")
            seen.add(plugin.id)
            plugins.append(plugin)
        return plugins

    def _parse(self, item: dict[str, Any]) -> Plugin:
        required = ("id", "name", "kind", "flatpak_id", "description")
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise ValueError(f"Plugin entry missing: {', '.join(missing)}")

        kind = item["kind"]
        if kind not in {"official_extension", "local_extension"}:
            raise ValueError(f"Unsupported plugin kind: {kind}")

        if kind == "local_extension":
            local_required = ("repository", "tag", "source_dir", "module_name")
            local_missing = [key for key in local_required if not item.get(key)]
            if local_missing:
                raise ValueError(
                    f"Local extension '{item['id']}' missing: {', '.join(local_missing)}"
                )
            if not str(item["flatpak_id"]).startswith(OBS_PLUGIN_PREFIX):
                raise ValueError(
                    f"Local extension '{item['id']}' must use an OBS plugin extension ID"
                )

        options = item.get("cmake_options", [])
        if not isinstance(options, list) or not all(isinstance(option, str) for option in options):
            raise ValueError(f"Plugin '{item['id']}' has invalid cmake_options")

        expected_commit = item.get("expected_commit")
        if expected_commit is not None and (
            not isinstance(expected_commit, str) or not expected_commit.strip()
        ):
            raise ValueError(f"Plugin '{item['id']}' has invalid expected_commit")

        required_obs_major = item.get("required_obs_major")
        if required_obs_major is not None and (
            not isinstance(required_obs_major, int) or required_obs_major < 1
        ):
            raise ValueError(f"Plugin '{item['id']}' has invalid required_obs_major")

        return Plugin(
            id=item["id"],
            name=item["name"],
            kind=kind,
            flatpak_id=item["flatpak_id"],
            description=item["description"],
            source=item.get("source"),
            repository=item.get("repository"),
            tag=item.get("tag"),
            expected_commit=expected_commit,
            source_dir=item.get("source_dir"),
            module_name=item.get("module_name"),
            required_obs_major=required_obs_major,
            cmake_options=tuple(options),
        )
