# DocumentSearch MCP Server

联网查询各大编程语言、游戏引擎、工具的文档。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

在 MCP 客户端配置中添加：

```json
{
  "mcpServers": {
    "doc-search": {
      "command": "python",
      "args": ["/path/to/DocumentSearch/server.py"]
    }
  }
}
```

## 工具

### search_docs
搜索文档，支持指定来源。

- `query` (必填): 搜索关键词
- `source` (可选): 限定搜索来源，使用 `list_sources` 查看可用 key
- `max_results` (可选): 最大结果数，默认 10

### list_sources
列出所有支持的文档来源。

- `category` (可选): 按分类筛选

### fetch_doc_page
获取文档页面的完整内容。

- `url` (必填): 文档页面 URL

## 支持来源

| 分类 | 来源 |
|------|------|
| 编程语言 | Python, JavaScript, TypeScript, Rust, Go, C++, C, Java, C#, Ruby, Swift, Kotlin, PHP, Lua, Zig |
| 游戏引擎 | Unity, Unreal Engine, Godot, Bevy, Cocos Creator |
| 框架 | React, Vue, Angular, Svelte, Next.js, Django, Flask, FastAPI, Rails, PyTorch, TensorFlow |
| 图形 | OpenGL, Vulkan, WebGPU, wgpu |
| 工具 | Docker, Kubernetes, Git, FFmpeg, CMake, LLVM |
| 数据库 | PostgreSQL, MySQL, MongoDB, Redis |
| 系统 | Linux Kernel |
| 库 | OpenCV |
