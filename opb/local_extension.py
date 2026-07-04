from __future__ import annotations

from pathlib import Path
import json
import re
import shutil

from opb.console import Console
from opb.flatpak import FlatpakManager, OBSInstall
from opb.process import ProcessRunner
from opb.registry import Plugin


class LocalExtensionBuilder:
    def __init__(
        self,
        project_root: Path,
        manager: FlatpakManager,
        runner: ProcessRunner,
        console: Console,
    ):
        self.project_root = project_root
        self.manager = manager
        self.runner = runner
        self.console = console

    def is_validly_installed(self, plugin: Plugin) -> bool:
        return bool(self.manager.extension_obs_modules(plugin.flatpak_id))

    def install(self, plugin: Plugin, obs: OBSInstall) -> None:
        if plugin.kind != "local_extension":
            raise ValueError(f"{plugin.id} is not a local extension")

        if self.manager.extension_is_installed(plugin.flatpak_id):
            if self.is_validly_installed(plugin):
                self.console.info(f"{plugin.name} is already installed and has an OBS module payload.")
                return
            self.console.info(
                f"{plugin.name} has an incomplete Flatpak extension payload. "
                "Removing it before rebuilding."
            )
            self.manager.uninstall_extension(plugin.flatpak_id)

        self._check_obs_compatibility(plugin, obs)

        assert plugin.repository and plugin.tag and plugin.source_dir and plugin.module_name
        root = self.project_root / "work" / plugin.id
        source_root = root / "sources"
        source_path = source_root / plugin.source_dir
        build_path = root / "build"
        manifest_path = root / f"{plugin.flatpak_id}.yml"
        metadata_path = root / "build-info.json"

        root.mkdir(parents=True, exist_ok=True)
        self.manager.ensure_sdk(obs.sdk_branch)

        shutil.rmtree(source_path, ignore_errors=True)
        shutil.rmtree(build_path, ignore_errors=True)

        self.runner.run(
            [
                "git", "clone", "--depth", "1", "--branch", plugin.tag,
                "--single-branch", "--recurse-submodules", plugin.repository,
                str(source_path),
            ]
        )

        commit = self._verified_commit(plugin, source_path)

        manifest_path.write_text(
            self._manifest(plugin, obs.sdk_branch), encoding="utf-8"
        )
        metadata_path.write_text(
            json.dumps(
                {
                    "plugin": plugin.id,
                    "flatpak_id": plugin.flatpak_id,
                    "extension_subdir": plugin.extension_subdir,
                    "repository": plugin.repository,
                    "tag": plugin.tag,
                    "commit": commit,
                    "sdk_branch": obs.sdk_branch,
                    "obs_version": obs.version,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        self.runner.run(
            [
                "flatpak-builder", "--user", "--install", "--force-clean",
                "--disable-download", str(build_path), str(manifest_path),
            ],
            cwd=root,
        )
        self._verify_installed_payload(plugin)

    def _check_obs_compatibility(self, plugin: Plugin, obs: OBSInstall) -> None:
        if plugin.required_obs_major is None:
            return

        installed_major = self._obs_major(obs.version)
        if installed_major is None:
            raise RuntimeError(
                f"Could not verify the installed OBS version for {plugin.name}. "
                f"This build recipe requires OBS {plugin.required_obs_major}.x."
            )
        if installed_major != plugin.required_obs_major:
            raise RuntimeError(
                f"{plugin.name} is pinned for OBS {plugin.required_obs_major}.x, "
                f"but this Flatpak OBS installation reports {obs.version or 'an unknown version'}. "
                "The manager stopped before building to avoid an ABI mismatch."
            )

    @staticmethod
    def _obs_major(version: str | None) -> int | None:
        if not version:
            return None
        match = re.match(r"\s*(\d+)", version)
        return int(match.group(1)) if match else None

    def _verified_commit(self, plugin: Plugin, source_path: Path) -> str:
        result = self.runner.run(["git", "rev-parse", "HEAD"], cwd=source_path)
        commit = result.stdout.strip()
        if not commit:
            raise RuntimeError("Could not read the cloned source commit.")
        if plugin.expected_commit and not commit.startswith(plugin.expected_commit):
            raise RuntimeError(
                f"Source verification failed for {plugin.name}. "
                f"Expected a commit beginning with {plugin.expected_commit}, got {commit}."
            )
        return commit

    def _verify_installed_payload(self, plugin: Plugin) -> None:
        modules = self.manager.extension_obs_modules(plugin.flatpak_id)
        if not modules:
            # Do not leave a mountable-but-empty extension behind.
            self.manager.uninstall_extension(plugin.flatpak_id)
            raise RuntimeError(
                f"{plugin.name} built, but Flatpak exported no .so file under "
                "files/lib/obs-plugins. The invalid extension was removed automatically."
            )
        self.console.info("Verified OBS module payload:")
        for module in modules:
            self.console.info(f"  {module}")

    def _manifest(self, plugin: Plugin, sdk_branch: str) -> str:
        options = "\n".join(f"      - {option}" for option in plugin.cmake_options)
        return f"""id: {plugin.flatpak_id}
branch: stable
runtime: com.obsproject.Studio
runtime-version: stable
sdk: org.freedesktop.Sdk//{sdk_branch}
build-extension: true
separate-locales: false
appstream-compose: false

# OBS mounts this extension at /app/plugins/{plugin.extension_subdir}.
# `libdir: lib` matters because this plugin template itself appends /obs-plugins.
build-options:
  prefix: /app/plugins/{plugin.extension_subdir}
  libdir: lib

modules:
  - name: {plugin.module_name}
    buildsystem: cmake-ninja
    builddir: true
    config-opts:
{options}
    sources:
      - type: dir
        path: sources/{plugin.source_dir}
"""
