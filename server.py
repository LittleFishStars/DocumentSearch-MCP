#!/usr/bin/env python3
"""MCP Server for searching documentation of programming languages, game engines, and tools.

Strategy:
  1. MDN API – JSON search for web docs (JS, CSS, HTML, Web APIs)
  2. docs.rs – HTML scraping for Rust crate search
  3. Direct search-page links – for all other sources
  4. fetch_doc_page – fetch and extract content from any doc URL
"""

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("doc-search")

UA = "Mozilla/5.0 (compatible; DocSearch-MCP/1.0)"

SUPPORTED: dict[str, dict] = {
    # ── programming_language ──────────────────────────────────────
    "python": {
        "name": "Python", "category": "programming_language",
        "sites": ["docs.python.org"],
        "desc": "Python language documentation",
        "search": "https://docs.python.org/3/search.html?q={q}",
    },
    "javascript": {
        "name": "JavaScript", "category": "programming_language",
        "sites": ["developer.mozilla.org"],
        "desc": "JavaScript (MDN) – direct API search",
        "search": "https://developer.mozilla.org/en-US/search?q={q}",
        "api": "mdn",
    },
    "typescript": {
        "name": "TypeScript", "category": "programming_language",
        "sites": ["typescriptlang.org"],
        "desc": "TypeScript language documentation",
        "search": "https://www.typescriptlang.org/search/?search={q}",
    },
    "rust": {
        "name": "Rust", "category": "programming_language",
        "sites": ["doc.rust-lang.org", "docs.rs"],
        "desc": "Rust std + crates (docs.rs direct search)",
        "search": "https://docs.rs/releases/search?query={q}",
        "api": "docsrs",
    },
    "go": {
        "name": "Go", "category": "programming_language",
        "sites": ["pkg.go.dev", "go.dev"],
        "desc": "Go package documentation",
        "search": "https://pkg.go.dev/search?q={q}",
    },
    "cpp": {
        "name": "C++", "category": "programming_language",
        "sites": ["en.cppreference.com"],
        "desc": "C++ reference",
        "search": "https://en.cppreference.com/mwiki/index.php?search={q}&title=Special%3ASearch",
    },
    "c": {
        "name": "C", "category": "programming_language",
        "sites": ["en.cppreference.com"],
        "desc": "C language reference",
        "search": "https://en.cppreference.com/mwiki/index.php?search={q}&title=Special%3ASearch",
    },
    "java": {
        "name": "Java", "category": "programming_language",
        "sites": ["docs.oracle.com"],
        "desc": "Java SE documentation",
        "search": "https://docs.oracle.com/en/java/javase/23/docs/api/search.html?q={q}",
    },
    "csharp": {
        "name": "C#", "category": "programming_language",
        "sites": ["learn.microsoft.com"],
        "desc": "C# / .NET documentation",
        "search": "https://learn.microsoft.com/en-us/dotnet/csharp/search/?search={q}",
    },
    "ruby": {
        "name": "Ruby", "category": "programming_language",
        "sites": ["docs.ruby-lang.org", "ruby-doc.org"],
        "desc": "Ruby documentation",
        "search": "https://docs.ruby-lang.org/en/master/search/index.html?q={q}",
    },
    "swift": {
        "name": "Swift", "category": "programming_language",
        "sites": ["developer.apple.com"],
        "desc": "Swift documentation",
        "search": "https://developer.apple.com/search/?q={q}",
    },
    "kotlin": {
        "name": "Kotlin", "category": "programming_language",
        "sites": ["kotlinlang.org"],
        "desc": "Kotlin documentation",
        "search": "https://kotlinlang.org/api/latest/jvm/stdlib/search.html?searchQuery={q}",
    },
    "php": {
        "name": "PHP", "category": "programming_language",
        "sites": ["php.net"],
        "desc": "PHP documentation",
        "search": "https://www.php.net/manual-lookup.php?pattern={q}&lang=en",
    },
    "lua": {
        "name": "Lua", "category": "programming_language",
        "sites": ["lua.org"],
        "desc": "Lua documentation",
        "search": "https://www.lua.org/cgi-bin/search3.cgi?keywords={q}",
    },
    "zig": {
        "name": "Zig", "category": "programming_language",
        "sites": ["ziglang.org"],
        "desc": "Zig documentation",
        "search": "https://ziglang.org/documentation/master/#{q}",
    },
    # ── game_engine ────────────────────────────────────────────────
    "unity": {
        "name": "Unity", "category": "game_engine",
        "sites": ["docs.unity3d.com", "docs.unity.com"],
        "desc": "Unity game engine",
        "search": "https://docs.unity3d.com/ScriptReference/Search.html?q={q}",
    },
    "unreal": {
        "name": "Unreal Engine", "category": "game_engine",
        "sites": ["docs.unrealengine.com", "dev.epicgames.com"],
        "desc": "Unreal Engine documentation",
        "search": "https://dev.epicgames.com/documentation/en-us/unreal-engine/search?q={q}",
    },
    "godot": {
        "name": "Godot", "category": "game_engine",
        "sites": ["docs.godotengine.org"],
        "desc": "Godot game engine",
        "search": "https://docs.godotengine.org/en/stable/search.html?q={q}&check_keywords=yes",
    },
    "bevy": {
        "name": "Bevy", "category": "game_engine",
        "sites": ["bevyengine.org"],
        "desc": "Bevy game engine (Rust)",
        "search": "https://bevyengine.org/learn/book/search/?q={q}",
    },
    "cocos": {
        "name": "Cocos Creator", "category": "game_engine",
        "sites": ["docs.cocos.com"],
        "desc": "Cocos Creator engine",
        "search": "https://docs.cocos.com/creator/manual/en/?q={q}",
    },
    # ── framework ──────────────────────────────────────────────────
    "react": {
        "name": "React", "category": "framework",
        "sites": ["react.dev"],
        "desc": "React framework",
        "search": "https://react.dev/search?q={q}",
    },
    "vue": {
        "name": "Vue.js", "category": "framework",
        "sites": ["vuejs.org"],
        "desc": "Vue.js framework",
        "search": "https://vuejs.org/search.html?query={q}",
    },
    "angular": {
        "name": "Angular", "category": "framework",
        "sites": ["angular.dev"],
        "desc": "Angular framework",
        "search": "https://angular.dev/search?search={q}",
    },
    "svelte": {
        "name": "Svelte", "category": "framework",
        "sites": ["svelte.dev"],
        "desc": "Svelte framework",
        "search": "https://svelte.dev/docs/search?q={q}",
    },
    "nextjs": {
        "name": "Next.js", "category": "framework",
        "sites": ["nextjs.org"],
        "desc": "Next.js framework",
        "search": "https://nextjs.org/search?q={q}",
    },
    "django": {
        "name": "Django", "category": "framework",
        "sites": ["docs.djangoproject.com"],
        "desc": "Django web framework",
        "search": "https://docs.djangoproject.com/en/stable/search/?q={q}",
    },
    "flask": {
        "name": "Flask", "category": "framework",
        "sites": ["flask.palletsprojects.com"],
        "desc": "Flask web framework",
        "search": "https://flask.palletsprojects.com/en/stable/search/?q={q}",
    },
    "fastapi": {
        "name": "FastAPI", "category": "framework",
        "sites": ["fastapi.tiangolo.com"],
        "desc": "FastAPI framework",
        "search": "https://fastapi.tiangolo.com/search/?q={q}",
    },
    "rails": {
        "name": "Ruby on Rails", "category": "framework",
        "sites": ["guides.rubyonrails.org", "api.rubyonrails.org"],
        "desc": "Ruby on Rails",
        "search": "https://guides.rubyonrails.org/search/?q={q}",
    },
    "pytorch": {
        "name": "PyTorch", "category": "framework",
        "sites": ["pytorch.org"],
        "desc": "PyTorch ML framework",
        "search": "https://pytorch.org/docs/stable/search.html?q={q}&check_keywords=yes",
    },
    "tensorflow": {
        "name": "TensorFlow", "category": "framework",
        "sites": ["tensorflow.org"],
        "desc": "TensorFlow ML framework",
        "search": "https://www.tensorflow.org/s/results?q={q}",
    },
    # ── graphics ───────────────────────────────────────────────────
    "opengl": {
        "name": "OpenGL", "category": "graphics",
        "sites": ["docs.gl", "registry.khronos.org"],
        "desc": "OpenGL API reference",
        "search": "http://docs.gl/?search={q}",
    },
    "vulkan": {
        "name": "Vulkan", "category": "graphics",
        "sites": ["registry.khronos.org", "docs.vulkan.org"],
        "desc": "Vulkan API reference",
        "search": "https://docs.vulkan.org/search.html?q={q}&check_keywords=yes",
    },
    "webgpu": {
        "name": "WebGPU", "category": "graphics",
        "sites": ["gpuweb.github.io", "developer.mozilla.org"],
        "desc": "WebGPU API documentation",
        "search": "https://developer.mozilla.org/en-US/search?q={q}+WebGPU",
    },
    "wgpu": {
        "name": "wgpu", "category": "graphics",
        "sites": ["docs.rs/wgpu"],
        "desc": "wgpu Rust graphics library",
        "search": "https://docs.rs/releases/search?query={q}+wgpu",
        "api": "docsrs",
    },
    # ── tool ───────────────────────────────────────────────────────
    "docker": {
        "name": "Docker", "category": "tool",
        "sites": ["docs.docker.com"],
        "desc": "Docker documentation",
        "search": "https://docs.docker.com/search/?q={q}",
    },
    "kubernetes": {
        "name": "Kubernetes", "category": "tool",
        "sites": ["kubernetes.io"],
        "desc": "Kubernetes documentation",
        "search": "https://kubernetes.io/search/?q={q}",
    },
    "git": {
        "name": "Git", "category": "tool",
        "sites": ["git-scm.com"],
        "desc": "Git documentation",
        "search": "https://git-scm.com/search/results?search={q}",
    },
    "ffmpeg": {
        "name": "FFmpeg", "category": "tool",
        "sites": ["ffmpeg.org"],
        "desc": "FFmpeg documentation",
        "search": "https://ffmpeg.org/search.html?q={q}",
    },
    "cmake": {
        "name": "CMake", "category": "tool",
        "sites": ["cmake.org"],
        "desc": "CMake build system",
        "search": "https://cmake.org/cmake/help/latest/search.html?q={q}&check_keywords=yes",
    },
    "llvm": {
        "name": "LLVM", "category": "tool",
        "sites": ["llvm.org"],
        "desc": "LLVM compiler docs",
        "search": "https://llvm.org/search/?q={q}",
    },
    # ── database ───────────────────────────────────────────────────
    "postgresql": {
        "name": "PostgreSQL", "category": "database",
        "sites": ["postgresql.org"],
        "desc": "PostgreSQL database",
        "search": "https://www.postgresql.org/search/?u=%2Fdocs%2Fcurrent%2F&q={q}",
    },
    "mysql": {
        "name": "MySQL", "category": "database",
        "sites": ["dev.mysql.com"],
        "desc": "MySQL database",
        "search": "https://dev.mysql.com/doc/search/?d=10&p=1&q={q}",
    },
    "mongodb": {
        "name": "MongoDB", "category": "database",
        "sites": ["mongodb.com"],
        "desc": "MongoDB database",
        "search": "https://www.mongodb.com/docs/search/?q={q}",
    },
    "redis": {
        "name": "Redis", "category": "database",
        "sites": ["redis.io"],
        "desc": "Redis documentation",
        "search": "https://redis.io/search/?q={q}",
    },
    # ── system ─────────────────────────────────────────────────────
    "linux": {
        "name": "Linux Kernel / man-pages", "category": "system",
        "sites": ["kernel.org", "man7.org"],
        "desc": "Linux kernel & man pages",
        "search": "https://man7.org/linux/man-pages/search.php?cmd=search&q={q}",
    },
    # ── library ────────────────────────────────────────────────────
    "opencv": {
        "name": "OpenCV", "category": "library",
        "sites": ["docs.opencv.org"],
        "desc": "OpenCV computer vision",
        "search": "https://docs.opencv.org/4.x/search.html?q={q}&check_keywords=yes",
    },
}

CATEGORIES = sorted(set(s["category"] for s in SUPPORTED.values()))


# ═══════════════════════════════════════════════════════════════════
#  Search backends
# ═══════════════════════════════════════════════════════════════════

async def _mdn_api(client: httpx.AsyncClient, query: str, n: int) -> list[dict]:
    """MDN search API – returns JSON."""
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


async def _docsrs(client: httpx.AsyncClient, query: str, n: int) -> list[dict]:
    """Scrape docs.rs search results page."""
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
        inner = m.group(2)
        title = re.sub(r"<[^>]+>", "", inner).strip()
        # skip nav-only links
        if len(title) < 5 or title in ("Docs.rs", "Rust", ""):
            continue
        # Try to extract snippet from surrounding context
        snippet = ""
        ctx = html[max(0, m.start() - 200):m.end() + 300]
        desc_m = re.search(r'<span[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</span>', ctx, re.DOTALL)
        if desc_m:
            snippet = _strip_html(desc_m.group(1))
        results.append({
            "title": title,
            "url": "https://docs.rs" + href,
            "snippet": snippet,
        })
    return results


async def _bing_fallback(client: httpx.AsyncClient, query: str, source_key: str | None, n: int) -> list[dict]:
    """Bing search with domain post-filter. Used when direct search fails."""
    source = SUPPORTED.get(source_key) if source_key else None
    sites = source["sites"] if source else []
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
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        snippet = _decode(_strip_html(snippet_m.group(1))) if snippet_m else ""
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if source_key and sites and not any(s in href for s in sites):
            continue
        results.append({"title": title, "url": href, "snippet": snippet})
    return results


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s).strip()


def _decode(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&#x27;", "'").replace("&nbsp;", " ")


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
            "Returns titles, URLs, and snippets from official doc sites.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'async/await', 'useState hook', 'Vec push'",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source key to restrict search (use list_sources to see all keys). Omit for all sources.",
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
            description=f"List all {len(SUPPORTED)} supported documentation sources with keys, categories, and descriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": f"Filter by category: {', '.join(CATEGORIES)}",
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
        for k, v in SUPPORTED.items():
            if cat and v["category"] != cat:
                continue
            items.append({
                "key": k, "name": v["name"], "category": v["category"],
                "description": v["desc"], "search_url": v["search"],
            })
        out = {"categories": CATEGORIES, "sources": items} if not cat else {"category": cat, "sources": items}
        return [TextContent(type="text", text=json.dumps(out, indent=2, ensure_ascii=False))]

    elif name == "search_docs":
        query = args["query"]
        source_key = args.get("source")
        max_results = min(args.get("max_results", 10), 20)

        if source_key and source_key not in SUPPORTED:
            return [TextContent(type="text", text=json.dumps(
                {"error": f"Unknown source '{source_key}'. Use list_sources."}, indent=2,
            ))]

        results: list[dict] = []
        search_url = ""
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # Strategy 1: Direct API
            src = SUPPORTED.get(source_key) if source_key else None
            api = src.get("api") if src else None

            if api == "mdn" or (not source_key):
                try:
                    results = await _mdn_api(client, query, max_results)
                    if source_key and results:
                        search_url = f"https://developer.mozilla.org/en-US/search?q={quote_plus(query)}"
                except Exception:
                    pass

            if api == "docsrs":
                try:
                    results = await _docsrs(client, query, max_results)
                    if results:
                        search_url = SUPPORTED[source_key]["search"].replace("{q}", quote_plus(query))
                except Exception:
                    pass

            # Strategy 2: Try direct search page for the specific source
            if not results and source_key and not api:
                try:
                    url = src["search"].replace("{q}", quote_plus(query))
                    resp = await client.get(url, headers={"User-Agent": UA})
                    search_url = url
                    # Try Sphinx/standard search result list patterns
                    html = resp.text
                    seen = set()
                    for pattern in [
                        r'<li[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
                        r'<a\s+href="([^"]+)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>',
                    ]:
                        for m in re.finditer(pattern, html, re.DOTALL):
                            if len(results) >= max_results:
                                break
                            href = m.group(1)
                            title = _decode(_strip_html(m.group(2))).strip()
                            if not title or title in seen or len(title) < 3:
                                continue
                            seen.add(title)
                            if href.startswith("#") or href.startswith("javascript:"):
                                continue
                            if not href.startswith("http"):
                                base = "/".join(url.split("/")[:3])
                                href = base + href if href.startswith("/") else base + "/" + href
                            results.append({"title": title, "url": href, "snippet": ""})
                except Exception:
                    pass

            # Strategy 3: Bing fallback
            if not results:
                try:
                    results = await _bing_fallback(client, query, source_key, max_results)
                except Exception:
                    pass

        source_name = SUPPORTED[source_key]["name"] if source_key else "all sources"
        output = {
            "query": query,
            "source": source_name,
            "source_key": source_key,
            "search_url": search_url or f"https://www.bing.com/search?q={quote_plus(query)}",
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
