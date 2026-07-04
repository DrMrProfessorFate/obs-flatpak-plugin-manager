from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import time
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


FORUM_ROOT = "https://obsproject.com"
PLUGIN_LIST_URL = f"{FORUM_ROOT}/forum/list/plugins.35/"
USER_AGENT = "OBS-Flatpak-Plugin-Manager/1.1 (candidate catalog; polite crawler)"
KNOWN_NAV_GITHUB_URLS = {
    "https://github.com/obsproject/obs-studio",
    "https://github.com/obsproject/obs-plugintemplate",
}


@dataclass(frozen=True)
class ForumThread:
    title: str
    url: str


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _fetch(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _hrefs(html: str) -> list[str]:
    parser = _HrefParser()
    parser.feed(html)
    return parser.hrefs


def _title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Untitled OBS Forum Thread"
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    return value.replace(" | OBS Forums", "").strip()


def _normalise_github_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"github.com", "www.github.com"}:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return None

    # Keep repository/release links useful but strip query strings and fragments.
    path = "/" + "/".join(path_parts)
    normalised = urlunparse(("https", "github.com", path.rstrip("/"), "", "", ""))
    if normalised.endswith(".git"):
        normalised = normalised[:-4]
    if normalised in KNOWN_NAV_GITHUB_URLS:
        return None
    return normalised


def _repository_key(github_url: str) -> str:
    parsed = urlparse(github_url)
    parts = [part for part in parsed.path.split("/") if part]
    return f"https://github.com/{parts[0]}/{parts[1]}"


class OBSForumGitHubDiscovery:
    """Builds an unreviewed candidate catalog from OBS Forum plugin threads.

    Candidates are never added to the installable registry automatically. Each plugin
    still needs a Flatpak extension manifest, dependency review, and compatibility test.
    """

    def __init__(self, output_path: Path, delay_seconds: float = 0.75):
        self.output_path = output_path
        self.delay_seconds = delay_seconds

    def discover(self, print_line=print) -> dict:
        print_line("Reading OBS Forums plugin index...")
        first_page = _fetch(PLUGIN_LIST_URL)
        page_count = self._detect_page_count(first_page)
        threads = self._collect_threads(first_page, page_count, print_line)

        print_line(f"Found {len(threads)} unique plugin threads.")
        print_line("Scanning first page of each thread for GitHub links...")

        candidates: dict[str, dict] = {}
        for index, thread in enumerate(threads, 1):
            print_line(f"  [{index}/{len(threads)}] {thread.title}")
            try:
                html = _fetch(thread.url)
                for href in _hrefs(html):
                    absolute = urljoin(thread.url, href)
                    github_url = _normalise_github_url(absolute)
                    if not github_url:
                        continue

                    repo = _repository_key(github_url)
                    entry = candidates.setdefault(
                        repo,
                        {
                            "repository": repo,
                            "github_urls": [],
                            "sources": [],
                            "review_status": "unreviewed",
                            "flatpak_compatible": None,
                            "installable": False,
                            "notes": "Discovered automatically. Review source, license, build system, Flatpak dependencies, and OBS compatibility before enabling installation.",
                        },
                    )
                    if github_url not in entry["github_urls"]:
                        entry["github_urls"].append(github_url)
                    source = {"title": thread.title, "url": thread.url}
                    if source not in entry["sources"]:
                        entry["sources"].append(source)
            except Exception as exc:
                print_line(f"    Warning: skipped thread after fetch error: {exc}")
            time.sleep(self.delay_seconds)

        payload = {
            "source": {
                "name": "OBS Forums Plugins",
                "url": PLUGIN_LIST_URL,
                "scope": "Public plugin-thread index and first page of each linked thread",
            },
            "generated_at_epoch": int(time.time()),
            "candidate_count": len(candidates),
            "candidates": sorted(candidates.values(), key=lambda item: item["repository"].lower()),
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def _detect_page_count(self, html: str) -> int:
        pages = [1]
        for href in _hrefs(html):
            absolute = urljoin(PLUGIN_LIST_URL, href)
            match = re.search(r"/forum/list/plugins\.35/page-(\d+)/?", absolute)
            if match:
                pages.append(int(match.group(1)))
        return max(pages)

    def _collect_threads(self, first_page: str, page_count: int, print_line) -> list[ForumThread]:
        seen: dict[str, ForumThread] = {}
        pages: Iterable[tuple[int, str]] = [(1, first_page)]
        for page in range(2, page_count + 1):
            print_line(f"  Fetching forum index page {page}/{page_count}...")
            url = f"{PLUGIN_LIST_URL}page-{page}"
            try:
                html = _fetch(url)
            except Exception as exc:
                print_line(f"    Warning: could not fetch page {page}: {exc}")
                continue
            pages = list(pages) + [(page, html)]
            time.sleep(self.delay_seconds)

        for _, html in pages:
            page_title = _title(html)
            for href in _hrefs(html):
                absolute = urljoin(PLUGIN_LIST_URL, href)
                if "/forum/threads/" not in absolute:
                    continue
                # Ignore thread page navigation links; retain canonical thread root.
                canonical = absolute.split("/page-")[0].rstrip("/") + "/"
                if canonical in seen:
                    continue
                seen[canonical] = ForumThread(title=page_title, url=canonical)
        return list(seen.values())
