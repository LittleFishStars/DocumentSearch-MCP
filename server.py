#!/usr/bin/env python3
"""MCP Server for searching documentation of programming languages, game engines, and tools.

Search backends (in priority order):
  1. MDN API          – native JSON search for Mozilla Developer Network
  2. docs.rs          – HTML scraping for Rust crate documentation
  3. Sphinx index     – parse searchindex.js for Python, Flask, Godot, etc.
  4. Bing fallback    – web search with domain post-filtering
"""

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("doc-search")

UA = "Mozilla/5.0 (compatible; DocSearch-MCP/1.0)"

CACHE_TTL = 1800  # 30 minute cache for search indexes

# ═══════════════════════════════════════════════════════════════════
#  Source definitions
# ═══════════════════════════════════════════════════════════════════

SOURCES: dict[str, dict] = {
    # ── programming_language ──────────────────────────────────────
    "python": {
        "name": "Python", "category": "programming_language",
        "desc": "Python language documentation (Sphinx searchindex)",
        "sites": ["docs.python.org"],
        "sphinx_base": "https://docs.python.org/3/",
        "sphinx_index": "https://docs.python.org/3/searchindex.js",
    },
    "javascript": {
        "name": "JavaScript", "category": "programming_language",
        "desc": "JavaScript/Web APIs (MDN native API)",
        "sites": ["developer.mozilla.org"],
        "api": "mdn",
    },
    "rust": {
        "name": "Rust", "category": "programming_language",
        "desc": "Rust crates (docs.rs search)",
        "sites": ["doc.rust-lang.org", "docs.rs"],
        "api": "docsrs",
    },
    "typescript": {
        "name": "TypeScript", "category": "programming_language",
        "desc": "TypeScript language docs",
        "sites": ["typescriptlang.org"],
        "search_url": "https://www.typescriptlang.org/search/?search={q}",
    },
    "go": {
        "name": "Go", "category": "programming_language",
        "desc": "Go standard library & packages",
        "sites": ["pkg.go.dev", "go.dev"],
        "search_url": "https://pkg.go.dev/search?q={q}",
    },
    "cpp": {
        "name": "C++", "category": "programming_language",
        "desc": "C++ reference (cppreference)",
        "sites": ["en.cppreference.com"],
        "search_url": "https://en.cppreference.com/mwiki/index.php?search={q}",
    },
    "c": {
        "name": "C", "category": "programming_language",
        "desc": "C language reference (cppreference)",
        "sites": ["en.cppreference.com"],
        "search_url": "https://en.cppreference.com/mwiki/index.php?search={q}&title=Special%3ASearch",
    },
    "java": {
        "name": "Java", "category": "programming_language",
        "desc": "Java SE documentation",
        "sites": ["docs.oracle.com"],
        "search_url": "https://docs.oracle.com/en/java/javase/23/docs/api/search.html?q={q}",
    },
    "csharp": {
        "name": "C#", "category": "programming_language",
        "desc": "C# / .NET (Microsoft Learn REST API)",
        "sites": ["learn.microsoft.com"],
        "api": "mslearn",
    },
    "ruby": {
        "name": "Ruby", "category": "programming_language",
        "desc": "Ruby language docs",
        "sites": ["docs.ruby-lang.org", "ruby-doc.org"],
        "search_url": "https://docs.ruby-lang.org/en/master/search/index.html?q={q}",
    },
    "swift": {
        "name": "Swift", "category": "programming_language",
        "desc": "Swift / Apple Developer",
        "sites": ["developer.apple.com"],
        "search_url": "https://developer.apple.com/search/?q={q}",
    },
    "kotlin": {
        "name": "Kotlin", "category": "programming_language",
        "desc": "Kotlin stdlib docs (Algolia DocSearch)",
        "sites": ["kotlinlang.org"],
        "api": "algolia",
        "algolia_app_id": "7961PKYRXV",
        "algolia_api_key": "1bfad5fdbae302b33d844ed1b43ec4d5",
        "algolia_index": "prod_KOTLINLANG_WEBHELP",
    },
    "php": {
        "name": "PHP", "category": "programming_language",
        "desc": "PHP manual",
        "sites": ["php.net"],
        "search_url": "https://www.php.net/manual-lookup.php?pattern={q}&lang=en",
    },
    "lua": {
        "name": "Lua", "category": "programming_language",
        "desc": "Lua reference manual",
        "sites": ["lua.org"],
        "search_url": "https://www.lua.org/cgi-bin/search3.cgi?keywords={q}",
    },
    "zig": {
        "name": "Zig", "category": "programming_language",
        "desc": "Zig language reference",
        "sites": ["ziglang.org"],
        "search_url": "https://ziglang.org/documentation/master/",
    },
    # ── game_engine ────────────────────────────────────────────────
    "unity": {
        "name": "Unity", "category": "game_engine",
        "desc": "Unity game engine manual & scripting",
        "sites": ["docs.unity3d.com"],
        "search_url": "https://docs.unity3d.com/Manual/30_search.html?q={q}",
    },
    "unreal": {
        "name": "Unreal Engine", "category": "game_engine",
        "desc": "Unreal Engine docs (Epic Dev)",
        "sites": ["docs.unrealengine.com", "dev.epicgames.com"],
        "search_url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/search?q={q}",
    },
    "godot": {
        "name": "Godot", "category": "game_engine",
        "desc": "Godot engine documentation (Sphinx)",
        "sites": ["docs.godotengine.org"],
        "sphinx_base": "https://docs.godotengine.org/en/stable/",
        "sphinx_index": "https://docs.godotengine.org/en/stable/searchindex.js",
    },
    "bevy": {
        "name": "Bevy", "category": "game_engine",
        "desc": "Bevy game engine (Rust)",
        "sites": ["bevyengine.org"],
        "search_url": "https://bevyengine.org/learn/book/search/?q={q}",
    },
    "cocos": {
        "name": "Cocos Creator", "category": "game_engine",
        "desc": "Cocos Creator game engine",
        "sites": ["docs.cocos.com"],
        "search_url": "https://docs.cocos.com/creator/manual/en/?q={q}",
    },
    # ── framework ──────────────────────────────────────────────────
    "react": {
        "name": "React", "category": "framework",
        "desc": "React framework (Algolia DocSearch)",
        "sites": ["react.dev"],
        "api": "algolia",
        "algolia_app_id": "1FCF9AYYAT",
        "algolia_api_key": "1b7ad4e1c89e645e351e59d40544eda1",
        "algolia_index": "beta-react",
    },
    "vue": {
        "name": "Vue.js", "category": "framework",
        "desc": "Vue.js framework (Algolia DocSearch)",
        "sites": ["vuejs.org"],
        "api": "algolia",
        "algolia_app_id": "ML0LEBN7FQ",
        "algolia_api_key": "10e7a8b13e6aec4007343338ab134e05",
        "algolia_index": "vuejs",
        "algolia_facet": "version:v3",
    },
    "angular": {
        "name": "Angular", "category": "framework",
        "desc": "Angular framework (Algolia DocSearch)",
        "sites": ["angular.dev"],
        "api": "algolia",
        "algolia_app_id": "L1XWT2UJ7F",
        "algolia_api_key": "dfca7ed184db27927a512e5c6668b968",
        "algolia_index": "angular_v17",
    },
    "svelte": {
        "name": "Svelte", "category": "framework",
        "desc": "Svelte framework",
        "sites": ["svelte.dev"],
        "search_url": "https://svelte.dev/docs/search?q={q}",
    },
    "nextjs": {
        "name": "Next.js", "category": "framework",
        "desc": "Next.js framework",
        "sites": ["nextjs.org"],
        "search_url": "https://nextjs.org/search?q={q}",
    },
    "django": {
        "name": "Django", "category": "framework",
        "desc": "Django web framework",
        "sites": ["docs.djangoproject.com"],
        "search_url": "https://docs.djangoproject.com/en/stable/search/?q={q}",
    },
    "flask": {
        "name": "Flask", "category": "framework",
        "desc": "Flask web framework (Sphinx)",
        "sites": ["flask.palletsprojects.com"],
        "sphinx_base": "https://flask.palletsprojects.com/en/stable/",
        "sphinx_index": "https://flask.palletsprojects.com/en/stable/searchindex.js",
    },
    "fastapi": {
        "name": "FastAPI", "category": "framework",
        "desc": "FastAPI framework",
        "sites": ["fastapi.tiangolo.com"],
        "search_url": "https://fastapi.tiangolo.com/search/?q={q}",
    },
    "rails": {
        "name": "Ruby on Rails", "category": "framework",
        "desc": "Ruby on Rails guides & API",
        "sites": ["guides.rubyonrails.org", "api.rubyonrails.org"],
        "search_url": "https://guides.rubyonrails.org/search/?q={q}",
    },
    "pytorch": {
        "name": "PyTorch", "category": "framework",
        "desc": "PyTorch ML framework (Sphinx)",
        "sites": ["pytorch.org"],
        "sphinx_base": "https://pytorch.org/docs/stable/",
        "sphinx_index": "https://pytorch.org/docs/stable/searchindex.js",
    },
    "tensorflow": {
        "name": "TensorFlow", "category": "framework",
        "desc": "TensorFlow ML framework",
        "sites": ["tensorflow.org"],
        "search_url": "https://www.tensorflow.org/s/results?q={q}",
    },
    # ── graphics ───────────────────────────────────────────────────
    "opengl": {
        "name": "OpenGL", "category": "graphics",
        "desc": "OpenGL API reference",
        "sites": ["docs.gl", "registry.khronos.org"],
        "search_url": "http://docs.gl/?search={q}",
    },
    "vulkan": {
        "name": "Vulkan", "category": "graphics",
        "desc": "Vulkan API docs (Sphinx)",
        "sites": ["registry.khronos.org", "docs.vulkan.org"],
        "sphinx_base": "https://docs.vulkan.org/",
        "sphinx_index": "https://docs.vulkan.org/searchindex.js",
    },
    "webgpu": {
        "name": "WebGPU", "category": "graphics",
        "desc": "WebGPU API (MDN + spec)",
        "sites": ["gpuweb.github.io", "developer.mozilla.org"],
        "search_url": "https://developer.mozilla.org/en-US/search?q={q}+WebGPU",
    },
    "wgpu": {
        "name": "wgpu", "category": "graphics",
        "desc": "wgpu Rust graphics library (docs.rs)",
        "sites": ["docs.rs/wgpu"],
        "api": "docsrs",
    },
    # ── tool ───────────────────────────────────────────────────────
    "docker": {
        "name": "Docker", "category": "tool",
        "desc": "Docker documentation",
        "sites": ["docs.docker.com"],
        "search_url": "https://docs.docker.com/search/?q={q}",
    },
    "kubernetes": {
        "name": "Kubernetes", "category": "tool",
        "desc": "Kubernetes docs",
        "sites": ["kubernetes.io"],
        "search_url": "https://kubernetes.io/docs/search/?q={q}",
    },
    "git": {
        "name": "Git", "category": "tool",
        "desc": "Git reference manual",
        "sites": ["git-scm.com"],
        "search_url": "https://git-scm.com/search/results?search={q}",
    },
    "ffmpeg": {
        "name": "FFmpeg", "category": "tool",
        "desc": "FFmpeg multimedia framework",
        "sites": ["ffmpeg.org"],
        "search_url": "https://ffmpeg.org/search.html?q={q}",
    },
    "cmake": {
        "name": "CMake", "category": "tool",
        "desc": "CMake build system (Sphinx)",
        "sites": ["cmake.org"],
        "sphinx_base": "https://cmake.org/cmake/help/latest/",
        "sphinx_index": "https://cmake.org/cmake/help/latest/searchindex.js",
    },
    "llvm": {
        "name": "LLVM", "category": "tool",
        "desc": "LLVM compiler infrastructure",
        "sites": ["llvm.org"],
        "search_url": "https://llvm.org/docs/Search.html?q={q}",
    },
    # ── database ───────────────────────────────────────────────────
    "postgresql": {
        "name": "PostgreSQL", "category": "database",
        "desc": "PostgreSQL database",
        "sites": ["postgresql.org"],
        "search_url": "https://www.postgresql.org/search/?u=%2Fdocs%2Fcurrent%2F&q={q}",
    },
    "mysql": {
        "name": "MySQL", "category": "database",
        "desc": "MySQL database docs",
        "sites": ["dev.mysql.com"],
        "search_url": "https://dev.mysql.com/doc/search/?d=10&p=1&q={q}",
    },
    "mongodb": {
        "name": "MongoDB", "category": "database",
        "desc": "MongoDB documentation",
        "sites": ["mongodb.com"],
        "search_url": "https://www.mongodb.com/docs/search/?q={q}",
    },
    "redis": {
        "name": "Redis", "category": "database",
        "desc": "Redis documentation",
        "sites": ["redis.io"],
        "search_url": "https://redis.io/search/?q={q}",
    },
    # ── system / library ───────────────────────────────────────────
    "linux": {
        "name": "Linux man-pages", "category": "system",
        "desc": "Linux kernel & man pages",
        "sites": ["kernel.org", "man7.org"],
        "search_url": "https://man7.org/linux/man-pages/search.php?cmd=search&q={q}",
    },
    "opencv": {
        "name": "OpenCV", "category": "library",
        "desc": "OpenCV computer vision library",
        "sites": ["docs.opencv.org"],
        "search_url": "https://docs.opencv.org/4.x/search.html?q={q}&check_keywords=yes",
    },
}

CATEGORIES = sorted(set(s["category"] for s in SOURCES.values()))


# ═══════════════════════════════════════════════════════════════════
#  Sphinx searchindex.js engine
# ═══════════════════════════════════════════════════════════════════

class SphinxIndex:
    """Downloads, parses, caches, and searches a Sphinx searchindex.js."""

    def __init__(self, index_url: str, base_url: str):
        self.index_url = index_url
        self.base_url = base_url.rstrip("/") + "/"
        self._docnames: list[str] = []
        self._filenames: list[str] = []
        self._titles: list[str] = []
        self._terms: dict[str, list[int]] = {}
        self._indexentries: dict[str, list] = {}
        self._objects: dict[str, list] = {}
        self._loaded_at: float = 0

    def _is_stale(self) -> bool:
        return time.time() - self._loaded_at > CACHE_TTL

    async def _ensure_loaded(self, client: httpx.AsyncClient) -> bool:
        if self._terms and not self._is_stale():
            return True
        try:
            resp = await client.get(self.index_url, headers={"User-Agent": UA}, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            self._parse(resp.text)
            self._loaded_at = time.time()
            return True
        except Exception:
            return bool(self._terms)

    def _parse(self, js_text: str) -> None:
        m = re.search(r"Search\.setIndex\((.*)\);?\s*$", js_text, re.DOTALL)
        if not m:
            return
        idx = json.loads(m.group(1))
        self._docnames = idx.get("docnames", [])
        self._filenames = idx.get("filenames", [])
        self._titles = idx.get("titles", [])
        self._terms = idx.get("terms", {})
        self._indexentries: dict[str, list] = idx.get("indexentries", {})
        self._objects: dict[str, list] = idx.get("objects", {})

    def search(self, query: str, max_results: int) -> list[dict]:
        if not self._terms:
            return []
        query_lower = query.lower()
        tokens = query_lower.split()
        total_docs = max(len(self._docnames), 1)
        results: list[dict] = []
        seen: set[int] = set()

        # Stage 1: Exact phrase matches from indexentries (highest priority)
        if self._indexentries:
            for phrase, entries in self._indexentries.items():
                phrase_lower = phrase.lower()
                # Only match if full query is a substring of the phrase, or vice versa
                if query_lower == phrase_lower or (len(query_lower) > 5 and query_lower in phrase_lower):
                    for entry in entries[:3]:
                        doc_idx = entry[0] if isinstance(entry, list) else entry
                        anchor = entry[1] if isinstance(entry, list) and len(entry) > 1 and isinstance(entry[1], str) else ""
                        if doc_idx not in seen and doc_idx < len(self._titles):
                            seen.add(doc_idx)
                            results.append(self._make_result(doc_idx, anchor, f"indexed: {phrase}"))

        # Stage 2: Token-based search
        scores: dict[int, float] = {}
        for token in tokens:
            if token in self._terms:
                indices = self._terms[token]
                df = len(indices)
                idf = 0.5 + (1.0 if df < total_docs * 0.03 else 0.3 if df < total_docs * 0.10 else 0.1)
                for di in indices:
                    if di not in seen:
                        scores[di] = scores.get(di, 0.0) + idf

        # Title phrase boost
        clean_titles = [_decode(_strip_html(t)).lower() for t in self._titles]
        for di, ct in enumerate(clean_titles):
            if di in seen:
                continue
            if query_lower in ct:
                scores[di] = scores.get(di, 0.0) + 3.0
            else:
                matched = sum(1 for t in tokens if t in ct)
                if matched >= len(tokens) * 0.6 and len(tokens) >= 2:
                    scores[di] = scores.get(di, 0.0) + matched * 0.5

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        for doc_idx, score in ranked:
            if len(results) >= max_results:
                break
            if doc_idx not in seen and doc_idx < len(self._titles):
                seen.add(doc_idx)
                results.append(self._make_result(doc_idx, "", f"score: {score:.2f}"))

        # Stage 3: Object matches (API names, class names, etc.)
        if self._objects and len(results) < max_results:
            for obj_name, obj_info in self._objects.items():
                obj_lower = obj_name.lower()
                if query_lower in obj_lower or (len(obj_lower) > 3 and obj_lower in query_lower):
                    doc_idx = obj_info[0] if isinstance(obj_info, list) else obj_info
                    anchor = obj_info[1] if isinstance(obj_info, list) and len(obj_info) > 1 and isinstance(obj_info[1], str) else ""
                    if doc_idx not in seen and doc_idx < len(self._titles):
                        seen.add(doc_idx)
                        results.append(self._make_result(doc_idx, anchor, f"object: {obj_name}"))

        return results[:max_results]

    def _make_result(self, doc_idx: int, anchor: str, snippet: str) -> dict:
        title_html = self._titles[doc_idx].strip() if doc_idx < len(self._titles) else "???"
        title = _decode(_strip_html(title_html))
        filename = self._filenames[doc_idx] if doc_idx < len(self._filenames) else "???"
        if filename.endswith(".rst"):
            filename = filename[:-4] + ".html"
        url = self.base_url + filename
        if anchor:
            url += "#" + anchor
        return {"title": title, "url": url, "snippet": snippet}


# Global Sphinx index cache
_sphinx_cache: dict[str, SphinxIndex] = {}


def _get_sphinx(source: dict) -> SphinxIndex | None:
    """Get or create a cached SphinxIndex for the given source."""
    idx_url = source.get("sphinx_index")
    base_url = source.get("sphinx_base")
    if not idx_url or not base_url:
        return None
    if idx_url not in _sphinx_cache:
        _sphinx_cache[idx_url] = SphinxIndex(idx_url, base_url)
    return _sphinx_cache[idx_url]


# ═══════════════════════════════════════════════════════════════════
#  Search backends
# ═══════════════════════════════════════════════════════════════════

async def _search_mdn(client: httpx.AsyncClient, query: str, n: int) -> list[dict]:
    url = f"https://developer.mozilla.org/api/v1/search?q={quote_plus(query)}&locale=en-US"
    resp = await client.get(url, headers={"User-Agent": UA})
    resp.raise_for_status()
    data = resp.json()
    results = []
    for doc in data.get("documents", [])[:n]:
        mdn_url = doc.get("mdn_url", "")
        if mdn_url and not mdn_url.startswith("http"):
            mdn_url = "https://developer.mozilla.org" + mdn_url
        results.append({
            "title": doc.get("title", ""),
            "url": mdn_url,
            "snippet": doc.get("summary", ""),
        })
    return results


async def _search_docsrs(client: httpx.AsyncClient, query: str, n: int) -> list[dict]:
    url = f"https://docs.rs/releases/search?query={quote_plus(query)}"
    resp = await client.get(url, headers={"User-Agent": UA})
    resp.raise_for_status()
    html = resp.text
    results = []
    for m in re.finditer(
        r'<a\s+href="(/[^"]+/latest/[^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    ):
        if len(results) >= n:
            break
        href = m.group(1)
        title = _decode(_strip_html(m.group(2)))
        if len(title) < 5 or title in ("Docs.rs", "Rust", ""):
            continue
        snippet = ""
        ctx = html[max(0, m.start() - 200):m.end() + 300]
        desc_m = re.search(r'<span[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</span>', ctx, re.DOTALL)
        if desc_m:
            snippet = _decode(_strip_html(desc_m.group(1)))
        results.append({"title": title, "url": "https://docs.rs" + href, "snippet": snippet})
    return results


async def _search_sphinx(
    client: httpx.AsyncClient, source: dict, query: str, n: int,
) -> list[dict]:
    idx = _get_sphinx(source)
    if not idx:
        return []
    ok = await idx._ensure_loaded(client)
    if not ok:
        return []
    return idx.search(query, n)


async def _search_generic(
    client: httpx.AsyncClient, source: dict, query: str, n: int,
) -> list[dict]:
    """Try the search URL directly and extract any server-rendered results."""
    url_tpl = source.get("search_url")
    if not url_tpl:
        return []
    url = url_tpl.replace("{q}", quote_plus(query))
    resp = await client.get(url, headers={"User-Agent": UA}, follow_redirects=True)
    html = resp.text
    results: list[dict] = []
    seen: set[str] = set()

    skip = (
        "next", "previous", "index", "modules", "home", "contents", "table of",
        "log in", "login", "sign in", "sign up", "create account", "register",
        "about", "about this site", "downloads", "download", "overview",
        "manual", "documentation", "api", "reference", "getting started",
        "learn", "en - english", "university", "apple developer",
        "documentation changelog", "frequently asked questions", "list of features",
        "python documentation contents", "glossary",
        "trademark", "tools command line", "footer navigation",
        "policies", "code of conduct", "your account", "community",
        "developers", "issues", "discussion", "get involved", "support us",
        "♥ donate", "|", "»", "«",
    )

    for m in re.finditer(r'<li[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        if len(results) >= n:
            break
        href = m.group(1)
        title = _decode(_strip_html(m.group(2)))
        if not title or len(title) < 5 or title in seen:
            continue
        title_lower = title.lower().strip()
        if any(title_lower == w or title_lower.startswith(w + " ") for w in skip):
            continue
        seen.add(title)
        if href.startswith("#") or href.startswith("javascript:") or href in ("/", ""):
            continue
        if not href.startswith("http"):
            base = "/".join(url.split("/")[:3])
            href = base + href if href.startswith("/") else base + "/" + href
        results.append({"title": title, "url": href, "snippet": ""})
    return results


async def _search_bing(
    client: httpx.AsyncClient, query: str, sites: list[str], n: int,
) -> list[dict]:
    domains_q = " OR ".join(sites) if sites else ""
    bing_q = f"{query} {domains_q}".strip()
    resp = await client.get(
        "https://www.bing.com/search",
        params={"q": bing_q, "count": min(n * 3, 20)},
        headers={"User-Agent": UA},
        follow_redirects=True,
    )
    html = resp.text
    results = []
    for block in re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL):
        if len(results) >= n:
            break
        m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not m:
            continue
        href = m.group(1)
        title = _decode(_strip_html(m.group(2)))
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        snippet = _decode(_strip_html(sm.group(1))) if sm else ""
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if sites and not any(s in href for s in sites):
            continue
        results.append({"title": title, "url": href, "snippet": snippet})
    return results


async def _search_algolia(
    client: httpx.AsyncClient, source: dict, query: str, n: int,
) -> list[dict]:
    """Search via Algolia DocSearch API."""
    app_id = source["algolia_app_id"]
    api_key = source["algolia_api_key"]
    index_name = source["algolia_index"]
    facet = source.get("algolia_facet")

    url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/query"
    body: dict = {
        "query": query,
        "hitsPerPage": n,
        "attributesToRetrieve": ["hierarchy", "url", "content"],
        "attributesToSnippet": ["content:30"],
    }
    if facet:
        body["facetFilters"] = [facet]

    resp = await client.post(
        url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
        },
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for hit in data.get("hits", [])[:n]:
        hl = hit.get("hierarchy", {})
        parts = [v for v in hl.values() if isinstance(v, str) and v]
        if parts:
            title = " > ".join(parts)
        elif hit.get("pageTitle"):
            title = hit["pageTitle"]
        elif hit.get("mainTitle"):
            title = hit["mainTitle"]
        else:
            title = hit.get("url", "").split("/")[-1].replace(".html", "").replace("-", " ") or query
        doc_url = hit.get("url", "")
        if doc_url and not doc_url.startswith("http"):
            site = source["sites"][0]
            doc_url = f"https://{site}{doc_url}" if doc_url.startswith("/") else f"https://{site}/{doc_url}"
        snippet = hit.get("_snippetResult", {}).get("content", {}).get("value", "")
        if not snippet:
            snippet = (hit.get("content", "") or "")[:100]
        if not snippet:
            snippet = title
        results.append({"title": title, "url": doc_url, "snippet": _decode(snippet)})
    return results


async def _search_mslearn(
    client: httpx.AsyncClient, source: dict, query: str, n: int,
) -> list[dict]:
    """Search via Microsoft Learn REST API."""
    url = f"https://learn.microsoft.com/api/search?search={quote_plus(query)}&locale=en-us&pageSize={n}"
    resp = await client.get(url, headers={"User-Agent": UA})
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", [])[:n]:
        title = item.get("title", "")
        doc_url = item.get("url", "")
        snippet = item.get("description", "")
        results.append({"title": title, "url": doc_url, "snippet": snippet})
    return results



# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s).strip()


def _decode(s: str) -> str:
    return (
        s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'").replace("&#x27;", "'")
        .replace("&nbsp;", " ").replace("&#64;", "@")
    )


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _extract_main(html: str) -> str:
    for tag in ("script", "style", "nav", "header", "footer"):
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)
    m = re.search(r"<(main|article)[^>]*>(.*?)</(main|article)>", html, re.DOTALL | re.IGNORECASE)
    if m:
        html = m.group(2)
    return _decode(_strip_html(html))


# ═══════════════════════════════════════════════════════════════════
#  MCP Tools
# ═══════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_docs",
            description="Search documentation for programming languages, game engines, frameworks, and tools. "
            "Uses native search APIs/indices for best results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. 'Vec push', 'useState', 'SELECT')",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source key (use list_sources to see all). Omit for all sources.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 10, max 20)",
                        "default": 10, "minimum": 1, "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_sources",
            description=f"List all {len(SOURCES)} supported documentation sources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": f"Filter by: {', '.join(CATEGORIES)}",
                    },
                },
            },
        ),
        Tool(
            name="fetch_doc_page",
            description="Fetch and extract main text content from a documentation page URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the documentation page",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, args: dict[str, Any]) -> list[TextContent]:
    if name == "list_sources":
        cat = args.get("category", "")
        items = []
        for k, v in SOURCES.items():
            if cat and v["category"] != cat:
                continue
            items.append({
                "key": k, "name": v["name"], "category": v["category"],
                "description": v["desc"],
                "backend": v.get("api", "sphinx" if "sphinx_index" in v else "search_url" if "search_url" in v else "bing"),
            })
        out = {"categories": CATEGORIES, "sources": items} if not cat else {"category": cat, "sources": items}
        return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]

    elif name == "search_docs":
        query = args["query"]
        source_key = args.get("source")
        max_n = min(args.get("max_results", 10), 20)

        if source_key and source_key not in SOURCES:
            return [TextContent(type="text", text=json.dumps(
                {"error": f"Unknown source '{source_key}'. Use list_sources."}, indent=2,
            ))]

        results: list[dict] = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            src = SOURCES.get(source_key) if source_key else None
            api = src.get("api") if src else None

            # Strategy 1: MDN API
            if api == "mdn" or (not source_key and not api):
                try:
                    results = await _search_mdn(client, query, max_n)
                except Exception:
                    pass

            # Strategy 2: docs.rs
            if api == "docsrs":
                try:
                    results = await _search_docsrs(client, query, max_n)
                except Exception:
                    pass

            # Strategy 3: Algolia DocSearch
            if api == "algolia":
                try:
                    results = await _search_algolia(client, src, query, max_n)
                except Exception:
                    pass

            # Strategy 4: Microsoft Learn
            if api == "mslearn":
                try:
                    results = await _search_mslearn(client, src, query, max_n)
                except Exception:
                    pass

            # Strategy 5: Sphinx searchindex.js
            if not results and src and src.get("sphinx_index"):
                try:
                    results = await _search_sphinx(client, src, query, max_n)
                except Exception:
                    pass

            # Strategy 6: Generic search URL
            if not results and src and src.get("search_url") and not api:
                try:
                    results = await _search_generic(client, src, query, max_n)
                except Exception:
                    pass

            # Strategy 7: Bing fallback
            if not results:
                try:
                    sites = src["sites"] if src else []
                    results = await _search_bing(client, query, sites, max_n)
                except Exception:
                    pass

        source_name = src["name"] if src else "all sources"
        output = {
            "query": query,
            "source": source_name,
            "source_key": source_key,
            "total_results": len(results),
            "results": results,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, ensure_ascii=False))]

    elif name == "fetch_doc_page":
        url = args["url"]
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers={"User-Agent": UA})
                resp.raise_for_status()
                text = _extract_main(resp.text)
                text = _clean(text)
                if len(text) > 8000:
                    text = text[:8000] + "\n\n... (truncated)"
                return [TextContent(type="text", text=json.dumps(
                    {"url": url, "content": text}, indent=2, ensure_ascii=False,
                ))]
            except Exception as e:
                return [TextContent(type="text", text=json.dumps(
                    {"error": f"Failed: {e}", "url": url}, indent=2,
                ))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
