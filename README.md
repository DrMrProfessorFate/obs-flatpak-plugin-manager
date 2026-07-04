# OBS Flatpak Plugin Manager v1.1.2

A portable, Flatpak-first bootstrap bundle for OBS Studio and a small curated list of plugins.

## What it does

1. Detects a supported host package manager.
2. Installs host prerequisites when missing: Flatpak, Flatpak Builder, Git, and Python 3.
3. Adds Flathub for the current user.
4. Installs a user-scoped copy of OBS Studio from Flathub when needed.
5. Installs official OBS Flatpak extensions from Flathub.
6. Builds vetted non-Flathub plugins as local user-scoped Flatpak extensions.
7. Records commands in `logs/manager.log` and source metadata in `work/<plugin>/build-info.json`.

## Curated plugins

- **Aitum Vertical Canvas** — official Flatpak extension from Flathub.
- **Branch Output** — local Flatpak extension built from upstream tag `1.0.9`.
- **Multiple RTMP Outputs** — local Flatpak extension built from upstream `0.7.3.2` at commit `fd41bfd…`. This recipe is intentionally guarded for **OBS 32.x only**.

## Run it

```bash
unzip obs-flatpak-plugin-manager-multi-rtmp.zip
cd obs-flatpak-plugin-manager-multi-rtmp
chmod +x bootstrap.sh run.sh
./bootstrap.sh
```

Then choose:

```text
2) Install one curated plugin
```

Select **Multiple RTMP Outputs**.

For a non-interactive batch run that installs every compatible curated entry:

```bash
./bootstrap.sh --yes --install-all
```

## Supported host package managers

- pacman (Arch, CachyOS, Manjaro)
- apt-get (Debian, Ubuntu, Pop!_OS, Mint)
- dnf (Fedora, RHEL-family systems where Flatpak Builder is available)
- zypper (openSUSE)
- xbps-install (Void)
- apk (Alpine)

For other distributions, install `flatpak`, `flatpak-builder`, `git`, and `python3` manually, add Flathub for your user, then run:

```bash
python3 builder.py
```

## Safety model

- The manager uses **user-scoped** Flatpak installs deliberately.
- It does not copy `.so` files into OBS config directories.
- Local plugins have a release tag and can optionally verify the source commit after cloning.
- A plugin can declare a required OBS major version; the manager stops before building when the installed OBS version does not match.
- Batch installs continue after an individual plugin failure.

## Adding another plugin

Do not add arbitrary GitHub repositories blindly. Review the plugin's source, build requirements, OBS ABI compatibility, runtime permissions, and Flatpak behavior first.

`registry/plugins.json` supports:

- `official_extension` — installed from Flathub by Flatpak ID.
- `local_extension` — source-built as a local user Flatpak extension.

A local extension needs its repository, immutable release tag, source directory, module name, and CMake options. Use `registry/PLUGIN_TEMPLATE.json` as a starting point. `expected_commit` and `required_obs_major` are optional but recommended when they are known.

## Discovering GitHub candidates safely

The manager can crawl the public OBS Forums Plugins index and make a **candidate-only** GitHub catalog. Nothing discovered there is added to the curated registry or installed automatically.

Run the manager, then choose:

```text
5) Discover GitHub URLs from OBS Forums Plugins (catalog only)
```

The output is `registry/discovered-github-candidates.json`.

## Version 1.1.1 fix

This release fixes OBS version detection for compatibility-guarded plugins such as Multiple RTMP Outputs. It uses Flatpak's documented `flatpak list --columns=application,version` output rather than the unsupported `flatpak info --show-version` option.

## Notes

- Fully close and reopen OBS after installing or removing an extension.
- The Multi RTMP upstream release used here is specifically labeled for OBS 32 and upstream does not distribute a Flatpak build, so this is a local build recipe rather than an official Flatpak package.
- A successful Flatpak build proves that the extension installed; test a private stream destination before using it in a live production.


## v1.1.2 packaging safeguard

Local OBS extensions are now verified after installation. The manager requires at least one module under `files/lib/obs-plugins/*.so`; an empty or wrongly staged extension is automatically removed instead of being reported as successful. Multi RTMP is staged under the Flatpak extension directory derived from its ID (`MultiRTMP`) and uses `libdir: lib`, matching the upstream CMake plugin template's own `obs-plugins` install suffix.
