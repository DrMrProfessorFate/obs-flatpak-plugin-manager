#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from opb.console import Console
from opb.discovery import OBSForumGitHubDiscovery
from opb.flatpak import FlatpakManager
from opb.local_extension import LocalExtensionBuilder
from opb.process import ProcessRunner, CommandError
from opb.registry import Registry, Plugin


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "registry" / "plugins.json"
CANDIDATES_PATH = ROOT / "registry" / "discovered-github-candidates.json"
LOG_PATH = ROOT / "logs" / "manager.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Portable Flatpak-first OBS plugin manager"
    )
    parser.add_argument(
        "--install-all",
        action="store_true",
        help="Install every enabled plugin in the curated registry.",
    )
    parser.add_argument(
        "--discover-obs-forum",
        action="store_true",
        help="Build an unreviewed GitHub candidate catalog from the OBS Forums Plugins index.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts. Intended for scripted use.",
    )
    return parser.parse_args()


def header(console: Console) -> None:
    console.header("OBS Flatpak Plugin Manager v1.1.2")
    console.info("Portable, user-scoped OBS + plugin bootstrap")
    console.info("Curated entries are installable; discovered GitHub URLs are catalog-only until reviewed.\n")


def ensure_environment(manager: FlatpakManager, console: Console, assume_yes: bool):
    missing = manager.host_tools_present()
    if missing:
        raise RuntimeError(
            "Missing host tools: " + ", ".join(missing) +
            ". Run ./bootstrap.sh first."
        )

    manager.ensure_user_flathub()
    obs = manager.ensure_user_obs(assume_yes=assume_yes)
    console.info("\nEnvironment ready:")
    console.info(f"  OBS version: {obs.version or 'unknown'}")
    console.info(f"  Runtime:     {obs.runtime}")
    console.info(f"  SDK branch:  {obs.sdk_branch}\n")
    return obs


def show_plugins(plugins: list[Plugin], manager: FlatpakManager, local_builder: LocalExtensionBuilder, console: Console) -> None:
    console.header("Curated installable plugin registry")
    for index, plugin in enumerate(plugins, 1):
        if plugin.kind == "local_extension" and manager.extension_is_installed(plugin.flatpak_id):
            status = "installed (verified)" if local_builder.is_validly_installed(plugin) else "installed (incomplete; rebuild needed)"
        else:
            status = "installed" if manager.extension_is_installed(plugin.flatpak_id) else "not installed"
        console.info(f"[{index}] {plugin.name} — {status}")
        console.info(f"    Type: {plugin.kind}")
        console.info(f"    {plugin.description}")
        if plugin.kind == "local_extension":
            console.info(f"    Pinned source: {plugin.tag}")
            if plugin.required_obs_major is not None:
                console.info(f"    Compatibility: OBS {plugin.required_obs_major}.x only")
        console.info("")


def install_plugin(
    plugin: Plugin,
    manager: FlatpakManager,
    local_builder: LocalExtensionBuilder,
    obs,
    console: Console,
    assume_yes: bool,
) -> bool:
    if plugin.kind == "official_extension" and manager.extension_is_installed(plugin.flatpak_id):
        console.info(f"Skipping {plugin.name}: already installed.")
        return True

    console.header(f"Install {plugin.name}")
    console.info(plugin.description)
    console.info(f"Extension ID: {plugin.flatpak_id}")
    if plugin.kind == "local_extension":
        console.info(f"Repository: {plugin.repository}")
        console.info(f"Pinned tag:  {plugin.tag}")
        if plugin.expected_commit:
            console.info(f"Commit check: {plugin.expected_commit}...")
        if plugin.required_obs_major is not None:
            console.info(f"Requires OBS: {plugin.required_obs_major}.x")
        console.info("Build location: this bundle's work/ directory")

    if not console.confirm("Proceed?", assume_yes=assume_yes):
        console.info("Skipped by user.")
        return False

    if plugin.kind == "official_extension":
        manager.install_official_extension(plugin.flatpak_id)
    elif plugin.kind == "local_extension":
        local_builder.install(plugin, obs)
    else:
        raise RuntimeError(f"Unsupported plugin kind: {plugin.kind}")

    console.info(f"Installed {plugin.name}.\n")
    return True


def install_all(
    plugins: list[Plugin],
    manager: FlatpakManager,
    local_builder: LocalExtensionBuilder,
    obs,
    console: Console,
    assume_yes: bool,
) -> None:
    console.header("Batch install")
    console.info("Plugins will be installed one at a time. Failures do not stop later entries.")
    if not console.confirm("Start batch installation?", assume_yes=assume_yes):
        console.info("Batch cancelled.")
        return

    failures: list[str] = []
    for plugin in plugins:
        try:
            install_plugin(plugin, manager, local_builder, obs, console, assume_yes=True)
        except Exception as exc:
            failures.append(plugin.name)
            console.error(f"{plugin.name} failed: {exc}")

    console.header("Batch summary")
    if failures:
        console.error("Failed: " + ", ".join(failures))
        console.info(f"Read the full log: {LOG_PATH}")
    else:
        console.info("All curated plugins installed successfully.")
    console.info("Fully close OBS and reopen it before using newly installed extensions.")


def discover_forum_candidates(console: Console, assume_yes: bool) -> None:
    console.header("Discover GitHub candidates from OBS Forums")
    console.info("This politely crawls the public OBS Forums Plugins index and the first page of each linked thread.")
    console.info("It extracts GitHub URLs into an unreviewed catalog only. Nothing is made installable or installed automatically.")
    console.info("This can take several minutes because it rate-limits requests.\n")
    if not console.confirm("Build/refresh the candidate catalog?", assume_yes=assume_yes):
        console.info("Discovery cancelled.")
        return

    discovery = OBSForumGitHubDiscovery(CANDIDATES_PATH)
    payload = discovery.discover(print_line=console.info)
    console.info(f"\nCatalog complete: {payload['candidate_count']} GitHub repository candidates.")
    console.info(f"Saved to: {CANDIDATES_PATH}")
    console.info("Review candidates before adding any to registry/plugins.json.\n")


def show_candidate_summary(console: Console) -> None:
    console.header("Discovered GitHub candidate catalog")
    if not CANDIDATES_PATH.exists():
        console.info("No catalog yet. Use discovery first.")
        return
    import json
    raw = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    candidates = raw.get("candidates", [])
    console.info(f"Candidates: {raw.get('candidate_count', len(candidates))}")
    console.info(f"Source: {raw.get('source', {}).get('url', 'unknown')}")
    console.info(f"File: {CANDIDATES_PATH}\n")
    for candidate in candidates[:20]:
        console.info(f"- {candidate['repository']} ({candidate['review_status']})")
    if len(candidates) > 20:
        console.info(f"\nShowing first 20 of {len(candidates)} candidates. Open the JSON file for the full list.")


def menu(
    plugins: list[Plugin],
    manager: FlatpakManager,
    local_builder: LocalExtensionBuilder,
    obs,
    console: Console,
) -> None:
    while True:
        header(console)
        console.info("1) Show curated installable plugin list and status")
        console.info("2) Install one curated plugin")
        console.info("3) Install all curated plugins")
        console.info("4) Remove one curated plugin")
        console.info("5) Discover GitHub URLs from OBS Forums Plugins (catalog only)")
        console.info("6) Show discovered candidate summary")
        console.info("7) Show log location")
        console.info("8) Quit\n")
        choice = input("> ").strip()

        if choice == "1":
            show_plugins(plugins, manager, local_builder, console)
            input("Press Enter to continue...")
        elif choice == "2":
            show_plugins(plugins, manager, local_builder, console)
            selected = input("Plugin number (or Enter to cancel): ").strip()
            if not selected:
                continue
            try:
                plugin = plugins[int(selected) - 1]
                install_plugin(plugin, manager, local_builder, obs, console, assume_yes=False)
            except (ValueError, IndexError):
                console.error("Invalid plugin selection.")
            except Exception as exc:
                console.error(str(exc))
                console.info(f"Read the full log: {LOG_PATH}")
            input("Press Enter to continue...")
        elif choice == "3":
            install_all(plugins, manager, local_builder, obs, console, assume_yes=False)
            input("Press Enter to continue...")
        elif choice == "4":
            show_plugins(plugins, manager, local_builder, console)
            selected = input("Plugin number to remove (or Enter to cancel): ").strip()
            if not selected:
                continue
            try:
                plugin = plugins[int(selected) - 1]
                if not manager.extension_is_installed(plugin.flatpak_id):
                    console.info("That plugin is not installed.")
                elif console.confirm(f"Remove {plugin.name}?"):
                    manager.uninstall_extension(plugin.flatpak_id)
                    console.info(f"Removed {plugin.name}.")
            except (ValueError, IndexError):
                console.error("Invalid plugin selection.")
            except Exception as exc:
                console.error(str(exc))
            input("Press Enter to continue...")
        elif choice == "5":
            discover_forum_candidates(console, assume_yes=False)
            input("Press Enter to continue...")
        elif choice == "6":
            show_candidate_summary(console)
            input("Press Enter to continue...")
        elif choice == "7":
            console.info(f"\nLog file: {LOG_PATH}\n")
            input("Press Enter to continue...")
        elif choice == "8":
            return
        else:
            console.error("Invalid selection.")


def main() -> int:
    args = parse_args()
    console = Console(LOG_PATH)
    runner = ProcessRunner(console)
    manager = FlatpakManager(runner, console)

    try:
        header(console)
        obs = ensure_environment(manager, console, assume_yes=args.yes)
        plugins = Registry(REGISTRY_PATH).load()
        local_builder = LocalExtensionBuilder(ROOT, manager, runner, console)

        if args.discover_obs_forum:
            discover_forum_candidates(console, assume_yes=args.yes)
        elif args.install_all:
            install_all(plugins, manager, local_builder, obs, console, assume_yes=args.yes)
        else:
            menu(plugins, manager, local_builder, obs, console)
        return 0
    except KeyboardInterrupt:
        console.info("\nCancelled.")
        return 130
    except (RuntimeError, CommandError, ValueError) as exc:
        console.error(str(exc))
        console.info(f"Read the full log: {LOG_PATH}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
