# Antigravity 适配规则与子智能体派发契约

本 harness 的主流程规范见 [docs/protocol.md](../../docs/protocol.md)（`init` 会把它复制进每个小说工作区的 `docs/protocol.md`）。

在 Antigravity 环境中运行本 harness 时，遵守以下派发与执行规则：

## 1. 角色与子智能体派发 (Subagent Dispatch)

`.agents/agents/`（即插件根目录 `agents/`）包含七个专业角色：
- `architect`：长篇规划师
- `planner`：单章细纲规划师
- `writer`：正文起草与修订
- `checker`：连续性检查员
- `editor`：主编（评审、合并检查报告、弧卷摘要）
- `ledger`：事实账本员
- `judge`：盲比裁决

### 派发流程：
1. **定义子智能体**：在会话中首次派发某角色前，先读取 `.agents/agents/<role>.md`，提取 frontmatter 中的描述与主体提示词，调用 `define_subagent`：
   - `name`: 角色名称（如 `architect`, `planner`, `writer`, `checker`, `editor`, `ledger`）
   - `description`: 角色的简述
   - `system_prompt`: 角色 md 文件去除 frontmatter 后的完整提示词
   - `enable_write_tools`: 若角色需要写入文件（除 checker/judge 外通常需要），设为 `true`；只读角色可设为 `false`
2. **派发执行**：使用 `invoke_subagent`：
   - `TypeName`: 角色名称
   - `Role`: 角色展示名
   - `Prompt`: 任务说明（必须包含：章节号、输入文件路径、输出文件路径、完成判据、不要做什么）
3. **并行派发**：
   - 路由为 `checker+editor` 时，在单次 `invoke_subagent` 调用中传入两个子智能体配置（`Subagents: [...]`），实现真正的并行执行。

## 2. 工具调用与自动化

- 所有事实层判定、路由查询、状态流转统一通过 `run_command` 调用工作区里的 `python3 tools/novel.py <command>`。新建工作区时先运行 `python3 <插件目录>/tools/novel.py init`，它会把 `tools/novel.py`、钩子与 `docs/` 契约复制进工作区。
- 绝不手工直接修改 `ledger/`、`state/`、`summaries/chapters/`、`index/`。
- 正文草稿只写入 `chapters/drafts/`，定稿由 `python3 tools/novel.py finalize N` 自动转入 `chapters/final/`。
