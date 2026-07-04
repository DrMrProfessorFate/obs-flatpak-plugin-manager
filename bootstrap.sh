#!/usr/bin/env bash
# OBS Flatpak Plugin Manager - portable bootstrapper
# Installs host prerequisites, configures a user-scoped Flathub remote,
# installs user-scoped OBS Studio if needed, then starts the manager.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASSUME_YES=0
RUN_ALL=0

usage() {
  cat <<'USAGE'
Usage: ./bootstrap.sh [--yes] [--install-all] [--help]

  --yes          Approve host-package, Flatpak remote, and OBS installation prompts.
  --install-all  Start the manager in batch mode after bootstrapping.
  --help         Show this help.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --install-all) RUN_ALL=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
warn() { printf '\nWARNING: %s\n' "$*" >&2; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

confirm() {
  local prompt="$1"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N] " answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    fail "This system needs administrator privileges to install host packages, but sudo is unavailable."
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

PACKAGE_MANAGER=""
if have pacman; then PACKAGE_MANAGER="pacman"
elif have apt-get; then PACKAGE_MANAGER="apt"
elif have dnf; then PACKAGE_MANAGER="dnf"
elif have zypper; then PACKAGE_MANAGER="zypper"
elif have xbps-install; then PACKAGE_MANAGER="xbps"
elif have apk; then PACKAGE_MANAGER="apk"
fi

if [[ -z "$PACKAGE_MANAGER" ]]; then
  fail "Unsupported package manager. Supported: pacman, apt, dnf, zypper, xbps, apk. Install flatpak, flatpak-builder, git, and python3 manually, then run python3 builder.py."
fi

missing=()
have flatpak || missing+=(flatpak)
have flatpak-builder || missing+=(flatpak-builder)
have git || missing+=(git)
have python3 || missing+=(python3)

if (( ${#missing[@]} > 0 )); then
  say "Missing host tools: ${missing[*]}"
  if ! confirm "Install the required host packages using $PACKAGE_MANAGER?"; then
    fail "Bootstrap cancelled."
  fi

  case "$PACKAGE_MANAGER" in
    pacman)
      run_root pacman -Syu --needed --noconfirm flatpak flatpak-builder git python
      ;;
    apt)
      run_root apt-get update
      run_root apt-get install -y flatpak flatpak-builder git python3
      ;;
    dnf)
      run_root dnf install -y flatpak flatpak-builder git python3
      ;;
    zypper)
      run_root zypper --non-interactive install flatpak flatpak-builder git python3
      ;;
    xbps)
      run_root xbps-install -Sy flatpak flatpak-builder git python3
      ;;
    apk)
      run_root apk add flatpak flatpak-builder git python3
      ;;
  esac
fi

say "Configuring the user-scoped Flathub remote"
flatpak --user remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

if ! flatpak info --user com.obsproject.Studio >/dev/null 2>&1; then
  say "User-scoped Flatpak OBS Studio is not installed"
  echo "This manager intentionally uses a user-scoped OBS installation so locally built extensions live in the same Flatpak installation."
  if ! confirm "Install OBS Studio for this user from Flathub?"; then
    fail "OBS installation cancelled."
  fi
  flatpak install --user -y flathub com.obsproject.Studio
fi

say "Starting OBS Flatpak Plugin Manager"
cd "$SCRIPT_DIR"
if [[ "$RUN_ALL" -eq 1 ]]; then
  exec python3 builder.py --install-all
else
  exec python3 builder.py
fi
