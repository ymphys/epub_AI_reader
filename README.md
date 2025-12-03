# reader 3 与 AI 集成

![reader3](reader3.png)

一个轻量、私有部署的 EPUB 阅读器，每次按章节逐步展示书籍内容，并在此基础上引入 DeepSeek AI 作为实时阅读助手。

本项目源自 reader3，90% 属于即兴实现；现在我们在其基础上加入 AI 功能，可以同步与 LLM 聊天、获取章节分析与问题答案。

## 概览

- **轻量阅读**：根据章节索引逐步呈现 EPUB 内容，界面简洁、高度可自定义。
- **自托管**：所有数据在本地，兼顾隐私与可控性。
- **阅读进度跟踪**：本地 SQLite 记录历史章节位置，可在不同设备之间同步（只要复制 `library/data/reading_progress.db`）。

## 功能亮点

### 核心阅读功能
- 按章节导航、可视化目录和图像渲染。
- 简单书库管理，已处理的书籍会列在库页面。
- 阅读进度以章节为单位，自动保存并展示上一章阅读位置。

### AI 加强功能
- **AI 聊天面板**：DeepSeek 提供实时问答，默认提示帮助总结当前章节并解释术语。
- **上下文感知**：AI 能读取当前章节文本并基于其提供回答。
- **章节分析**：支持自动生成摘要、词语解释与概念拆解。
- **问题解答**：可对当前章节提出任意问题，AI 会在带上下文的基础上回复。
- **中文支持**：完整中文版界面和默认提示，适配中文阅读习惯。

## 使用说明

### 库结构（默认路径）
- `library/epubs/`：原始 EPUB 文件存放地。
- `library/data/`：处理后 `_data` 目录、AI 缓存和 `reading_progress.db`。
- 环境变量 `LIBRARY_ROOT`、`LIBRARY_EPUB_DIR`、`LIBRARY_DATA_DIR` 可覆盖这些路径。

### 1. 处理 EPUB

```bash
uv run reader3.py dracula.epub
```

`reader3.py` 支持直接引用 `library/epubs/` 下的文件，并把章节数据存储在 `library/data/dracula_data/`。

### 2. 预先生成 AI 缓存（推荐）

```bash
uv run generate_ai_cache.py dracula_data
```

该脚本会遍历每个章节、调用 DeepSeek 的默认提示（超过 2,000 字会截断）、把返回结果写入 `default_ai_cache.json`，读者打开章节时即可即时看到总结与解释（无需等待网络）。

默认提示保存也写入缓存文件；如果想重新生成整本书的默认问答，可加 `--force`。

### 3. 配置 AI（可选）

确保已设置 DeepSeek API 密钥：

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key_here"
```

### 4. 启动服务器

```bash
uv run server.py
```

访问 [http://localhost:8123](http://localhost:8123) 查看书库，选中任意书后点击 “Read with AI”。

## AI 阅读体验

1. 在书库页点击 “Read with AI”，默认位置从上次阅读章节继续。
2. AI 侧边栏名为 DeepSeek AI，默认会显示一条问候并自动发送摘要请求。
3. 你可以手动输入问题或直接回复，AI 会实时返回答案并保存到 `default_ai_cache.json` 中。
4. 所有章节缓存的问答会随章节加载并在页面刷新后恢复，方便整理笔记。

### 示例提问
- “请总结这一章的主要内容。”
- “解释一下这个概念。”
- “这个人物在故事中扮演什么角色？”
- “这个技术术语是什么意思？”

### 阅读进度追踪
- **继续阅读**：自动恢复至上次所读章节。
- **进度可视化**：库页面显示章节总数和最后阅读位置。
- **标记完成**：库页可把书标记为“Done Reading”，已读书籍会移到下方并与当前阅读区隔离。
- **跨设备同步**：只需复制 `library/data/reading_progress.db` 即可迁移进度。

## 技术细节

- `reader3.py`：EPUB 解析器，提取目录、章节和图像。支持内置库路径智能查找。
- `server.py`：FastAPI 服务器，提供普通阅读页面、AI 阅读页面、图像、聊天 API 与书库接口。
- `deepseek_client.py`：封装 DeepSeek API 调用。
- `generate_ai_cache.py`：离线生成默认问答缓存。
- `templates/reader_with_ai.html`：AI 阅读器 UI。
- `templates/library.html`：带进度和完成区分的库页面。

## AI 集成说明

- 使用 DeepSeek 聊天 API；默认 prompt 限制上下文为 2,000 字。
- 支持实时对话、默认问答和手动提问自动保存。
- 错误会在页面和日志中提示，便于排查。

## 许可证

MIT

## 说明

- 本项目仅供参考，可自行修改。 
- 未提供官方技术支持。
- AI 功能需有效的 DeepSeek API 密钥。
- 请注意 DeepSeek 的调用次数和费用。

## 故障排查

### AI 功能无法使用
- 确认 `DEEPSEEK_API_KEY` 已设置。
- 检查密钥是否仍然有效。
- 查看服务器日志输出。

### 阅读进度出问题
- 进度保存在 `library/data/reading_progress.db`。
- 删除该文件会清空所有记录。

### 其他问题
- 使用 `uv sync` 安装依赖。
- 确认 EPUB 正确处理并生成 `_data` 目录。
- 确保 `server.py` 在 8123 端口运行。
