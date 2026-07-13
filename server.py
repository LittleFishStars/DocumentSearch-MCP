#!/usr/bin/env python3
"""MCP Server for searching documentation across programming languages, game engines, and tools."""

import asyncio
import json
import re
from typing import Any

import httpx
from duckduckgo_search import DDGS
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("doc-search")

SUPPORTED_SOURCES = {
    "python": {
        "name": "Python",
        "category": "programming_language",
        "sites": ["docs.python.org", "python.org"],
        "description": "Python programming language documentation",
    },
    "javascript": {
        "name": "JavaScript",
        "category": "programming_language",
        "sites": ["developer.mozilla.org", "javascript.info"],
        "description": "JavaScript (MDN) documentation",
    },
    "typescript": {
        "name": "TypeScript",
        "category": "programming_language",
        "sites": ["typescriptlang.org"],
        "description": "TypeScript language documentation",
    },
    "rust": {
        "name": "Rust",
        "category": "programming_language",
        "sites": ["doc.rust-lang.org", "docs.rs"],
        "description": "Rust programming language documentation",
    },
    "go": {
        "name": "Go",
        "category": "programming_language",
        "sites": ["pkg.go.dev", "go.dev"],
        "description": "Go programming language documentation",
    },
    "cpp": {
        "name": "C++",
        "category": "programming_language",
        "sites": ["cppreference.com", "isocpp.org"],
        "description": "C++ reference and documentation",
    },
    "c": {
        "name": "C",
        "category": "programming_language",
        "sites": ["cppreference.com"],
        "description": "C language reference documentation",
    },
    "java": {
        "name": "Java",
        "category": "programming_language",
        "sites": ["docs.oracle.com/javase"],
        "description": "Java SE documentation",
    },
    "csharp": {
        "name": "C#",
        "category": "programming_language",
        "sites": ["learn.microsoft.com/en-us/dotnet/csharp"],
        "description": "C# .NET documentation",
    },
    "ruby": {
        "name": "Ruby",
        "category": "programming_language",
        "sites": ["docs.ruby-lang.org", "ruby-doc.org"],
        "description": "Ruby programming language documentation",
    },
    "swift": {
        "name": "Swift",
        "category": "programming_language",
        "sites": ["developer.apple.com/documentation/swift"],
        "description": "Swift programming language documentation",
    },
    "kotlin": {
        "name": "Kotlin",
        "category": "programming_language",
        "sites": ["kotlinlang.org"],
        "description": "Kotlin programming language documentation",
    },
    "php": {
        "name": "PHP",
        "category": "programming_language",
        "sites": ["php.net"],
        "description": "PHP documentation",
    },
    "lua": {
        "name": "Lua",
        "category": "programming_language",
        "sites": ["lua.org/manual"],
        "description": "Lua programming language documentation",
    },
    "zig": {
        "name": "Zig",
        "category": "programming_language",
        "sites": ["ziglang.org/documentation"],
        "description": "Zig programming language documentation",
    },
    "unity": {
        "name": "Unity",
        "category": "game_engine",
        "sites": ["docs.unity3d.com", "docs.unity.com"],
        "description": "Unity game engine documentation",
    },
    "unreal": {
        "name": "Unreal Engine",
        "category": "game_engine",
        "sites": ["docs.unrealengine.com", "dev.epicgames.com"],
        "description": "Unreal Engine documentation",
    },
    "godot": {
        "name": "Godot",
        "category": "game_engine",
        "sites": ["docs.godotengine.org"],
        "description": "Godot game engine documentation",
    },
    "bevy": {
        "name": "Bevy",
        "category": "game_engine",
        "sites": ["bevyengine.org", "docs.rs/bevy"],
        "description": "Bevy game engine documentation",
    },
    "cocos": {
        "name": "Cocos Creator",
        "category": "game_engine",
        "sites": ["docs.cocos.com"],
        "description": "Cocos Creator documentation",
    },
    "docker": {
        "name": "Docker",
        "category": "tool",
        "sites": ["docs.docker.com"],
        "description": "Docker documentation",
    },
    "kubernetes": {
        "name": "Kubernetes",
        "category": "tool",
        "sites": ["kubernetes.io/docs"],
        "description": "Kubernetes documentation",
    },
    "git": {
        "name": "Git",
        "category": "tool",
        "sites": ["git-scm.com/docs"],
        "description": "Git documentation",
    },
    "react": {
        "name": "React",
        "category": "framework",
        "sites": ["react.dev", "reactjs.org"],
        "description": "React framework documentation",
    },
    "vue": {
        "name": "Vue.js",
        "category": "framework",
        "sites": ["vuejs.org"],
        "description": "Vue.js framework documentation",
    },
    "angular": {
        "name": "Angular",
        "category": "framework",
        "sites": ["angular.dev", "angular.io"],
        "description": "Angular framework documentation",
    },
    "svelte": {
        "name": "Svelte",
        "category": "framework",
        "sites": ["svelte.dev"],
        "description": "Svelte framework documentation",
    },
    "nextjs": {
        "name": "Next.js",
        "category": "framework",
        "sites": ["nextjs.org"],
        "description": "Next.js framework documentation",
    },
    "django": {
        "name": "Django",
        "category": "framework",
        "sites": ["docs.djangoproject.com"],
        "description": "Django web framework documentation",
    },
    "flask": {
        "name": "Flask",
        "category": "framework",
        "sites": ["flask.palletsprojects.com"],
        "description": "Flask web framework documentation",
    },
    "fastapi": {
        "name": "FastAPI",
        "category": "framework",
        "sites": ["fastapi.tiangolo.com"],
        "description": "FastAPI framework documentation",
    },
    "rails": {
        "name": "Ruby on Rails",
        "category": "framework",
        "sites": ["guides.rubyonrails.org", "api.rubyonrails.org"],
        "description": "Ruby on Rails documentation",
    },
    "pytorch": {
        "name": "PyTorch",
        "category": "framework",
        "sites": ["pytorch.org/docs"],
        "description": "PyTorch machine learning framework documentation",
    },
    "tensorflow": {
        "name": "TensorFlow",
        "category": "framework",
        "sites": ["tensorflow.org"],
        "description": "TensorFlow documentation",
    },
    "opengl": {
        "name": "OpenGL",
        "category": "graphics",
        "sites": ["docs.gl", "registry.khronos.org/OpenGL"],
        "description": "OpenGL API documentation",
    },
    "vulkan": {
        "name": "Vulkan",
        "category": "graphics",
        "sites": ["registry.khronos.org/vulkan", "docs.vulkan.org"],
        "description": "Vulkan API documentation",
    },
    "webgpu": {
        "name": "WebGPU",
        "category": "graphics",
        "sites": ["gpuweb.github.io/gpuweb", "developer.mozilla.org/en-US/docs/Web/API/WebGPU_API"],
        "description": "WebGPU API documentation",
    },
    "wgpu": {
        "name": "wgpu",
        "category": "graphics",
        "sites": ["docs.rs/wgpu"],
        "description": "wgpu Rust graphics library documentation",
    },
    "opencv": {
        "name": "OpenCV",
        "category": "library",
        "sites": ["docs.opencv.org"],
        "description": "OpenCV computer vision library documentation",
    },
    "ffmpeg": {
        "name": "FFmpeg",
        "category": "tool",
        "sites": ["ffmpeg.org/documentation.html"],
        "description": "FFmpeg documentation",
    },
    "cmake": {
        "name": "CMake",
        "category": "tool",
        "sites": ["cmake.org/documentation", "cmake.org/cmake/help"],
        "description": "CMake build system documentation",
    },
    "llvm": {
        "name": "LLVM",
        "category": "tool",
        "sites": ["llvm.org/docs"],
        "description": "LLVM compiler infrastructure documentation",
    },
    "linux": {
        "name": "Linux Kernel",
        "category": "system",
        "sites": ["kernel.org/doc", "man7.org/linux/man-pages"],
        "description": "Linux kernel and man page documentation",
    },
    "postgresql": {
        "name": "PostgreSQL",
        "category": "database",
        "sites": ["postgresql.org/docs"],
        "description": "PostgreSQL database documentation",
    },
    "mysql": {
        "name": "MySQL",
        "category": "database",
        "sites": ["dev.mysql.com/doc"],
        "description": "MySQL database documentation",
    },
    "mongodb": {
        "name": "MongoDB",
        "category": "database",
        "sites": ["mongodb.com/docs"],
        "description": "MongoDB database documentation",
    },
    "redis": {
        "name": "Redis",
        "category": "database",
        "sites": ["redis.io/docs"],
        "description": "Redis documentation",
    },
}

CATEGORIES = sorted(set(s["category"] for s in SUPPORTED_SOURCES.values()))


def build_search_query(query: str, source_key: str | None) -> str:
    """Build a site-specific or general search query."""
    if source_key and source_key in SUPPORTED_SOURCES:
        source = SUPPORTED_SOURCES[source_key]
        site_filter = " OR ".join(f"site:{s}" for s in source["sites"])
        return f"{query} ({site_filter})"
    return query


def format_results(results: list[dict], max_results: int = 10) -> list[dict]:
    """Format and limit search results."""
    formatted = []
    for r in results[:max_results]:
        formatted.append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        })
    return formatted


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_docs",
            description="Search documentation for programming languages, game engines, frameworks, and tools. "
            "Returns relevant documentation pages with titles, URLs, and snippets.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'async/await', 'array methods', 'collision detection')",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source key to restrict search to specific documentation. "
                        "Use list_sources to see available keys. "
                        "If omitted, searches across all sources.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10, max: 20)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_sources",
            description="List all supported documentation sources with their keys, categories, and descriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category. Available categories: "
                        + ", ".join(CATEGORIES),
                    },
                },
            },
        ),
        Tool(
            name="fetch_doc_page",
            description="Fetch and extract the main content from a documentation page URL. "
            "Useful for reading the full content of a result from search_docs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the documentation page to fetch",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "list_sources":
        category = arguments.get("category", "")
        sources_list = []
        for key, info in SUPPORTED_SOURCES.items():
            if category and info["category"] != category:
                continue
            sources_list.append({
                "key": key,
                "name": info["name"],
                "category": info["category"],
                "description": info["description"],
                "sites": info["sites"],
            })
        if category:
            result = {"category": category, "sources": sources_list}
        else:
            result = {"categories": CATEGORIES, "sources": sources_list}
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

    elif name == "search_docs":
        query = arguments["query"]
        source_key = arguments.get("source")
        max_results = min(arguments.get("max_results", 10), 20)

        if source_key and source_key not in SUPPORTED_SOURCES:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Unknown source '{source_key}'. Use list_sources to see available keys."
                }, indent=2),
            )]

        search_query = build_search_query(query, source_key)

        loop = asyncio.get_running_loop()
        try:
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(search_query, max_results=max_results)),
            )
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Search failed: {str(e)}"}, indent=2),
            )]

        formatted = format_results(results, max_results)
        source_name = SUPPORTED_SOURCES[source_key]["name"] if source_key else "all sources"
        output = {
            "query": query,
            "source": source_name,
            "source_key": source_key,
            "total_results": len(formatted),
            "results": formatted,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, ensure_ascii=False))]

    elif name == "fetch_doc_page":
        url = arguments["url"]
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; DocSearchBot/1.0)",
                    },
                )
                response.raise_for_status()
                html = response.text
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Failed to fetch page: {str(e)}"}, indent=2),
            )]

        text = extract_main_content(html)
        text = clean_text(text)
        if len(text) > 8000:
            text = text[:8000] + "\n\n... (truncated)"

        return [TextContent(
            type="text",
            text=json.dumps({"url": url, "content": text}, indent=2, ensure_ascii=False),
        )]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def extract_main_content(html: str) -> str:
    """Extract main textual content from HTML using simple heuristics."""
    # Remove script and style elements
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Try to find main content area
    main_match = re.search(
        r"<(main|article)[^>]*>(.*?)</(main|article)>",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if main_match:
        html = main_match.group(2)

    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = text.replace("&#x27;", "'")
    return text


def clean_text(text: str) -> str:
    """Clean up extracted text."""
    # Collapse multiple whitespace/newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.splitlines()]
    # Remove empty lines at start/end
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
