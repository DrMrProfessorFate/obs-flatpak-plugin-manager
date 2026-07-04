# OBS Forum GitHub Candidate Discovery

The manager can build a **candidate-only** catalog from the public OBS Forums Plugins index.

It follows the forum's plugin listing pages, then scans the first page of each linked plugin thread for GitHub links. Requests are deliberately rate-limited. The catalog is saved to:

```text
registry/discovered-github-candidates.json
```

## Important safety rule

Discovered URLs are **not** added to `registry/plugins.json` and cannot be installed by the batch installer. They are unreviewed candidates only.

A plugin can be Windows-only, deprecated, a script rather than a compiled plugin, incompatible with your OBS version, dependent on host binaries, or unsuitable for the Flatpak sandbox. Each candidate needs a reviewed Flatpak extension manifest before it becomes installable.

## Use

Interactive mode:

```bash
./run.sh
```

Choose:

```text
5) Discover GitHub URLs from OBS Forums Plugins (catalog only)
```

Non-interactive discovery:

```bash
python3 builder.py --discover-obs-forum --yes
```

The scan may take several minutes. It intentionally does not crawl every reply page in each thread, only the first thread page.
