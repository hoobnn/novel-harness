# 运行时适配（已按官方文档核实，2026-10-02）

角色只维护一份源 `agents/<role>.md`（Claude Code 格式）。除 Claude Code 插件之外的所有运行时都走同一条路：
`python3 tools/novel.py init --standalone [--runtime …]` 在工作区生成各运行时自己的子智能体定义、skill 副本、
AGENTS.md 与钩子；`novel.py upgrade` 按 `state/progress.json` 里记录的 `standalone_runtimes` 重新生成。

| 运行时 | 子智能体定义（生成物） | skill 目录 | 指令文件 | 派发写法 | 钩子 |
|---|---|---|---|---|---|
| Claude Code（插件） | 插件自带 `agents/` | 插件自带 | 工作区 CLAUDE.md | Agent 工具，`novel-harness:writer` | 插件 `hooks/hooks.json` |
| Claude Code（standalone） | `.claude/agents/<role>.md` 原样复制 | `.claude/skills/` | CLAUDE.md | Agent 工具，`writer` | `.claude/settings.json` |
| Cursor | 不生成：原生读取 `.claude/agents/` | `.agents/skills/`（也读 `.claude/skills/`） | AGENTS.md | `/writer` 或自然语言点名，多次 Task 并行 | 合并 `.claude/settings.json` 的 PostToolUse |
| Codex | `.codex/agents/<role>.toml` | `.agents/skills/` | AGENTS.md | 指令里点名角色，`$novel-next` 调 skill | 无 |
| OpenCode | `.opencode/agents/<role>.md` | `.agents/skills/`（也读 `.claude/skills/`） | AGENTS.md（无则 CLAUDE.md） | `@writer` 或按描述自动 | 仅 JS 插件，未提供 |
| Antigravity | `.agents/agents/<role>.md` | `.agents/skills/` | AGENTS.md / GEMINI.md | `invoke_subagent`，一次传多个 spec 即并行 | `.agents/hooks.json` 的 PostToolUse 不能回馈，未提供 |
| Pi | `.pi/agents/<role>.md` | `.agents/skills/`、`.pi/skills/` | AGENTS.md / CLAUDE.md | 需装 `examples/extensions/subagent` 且 `agentScope` 含 project | 仅 TS 扩展，未提供 |

没有钩子的运行时不影响正确性：writer 角色自己跑 `lint`，`novel.py commit` 提交前再校验一次事实。

## 字段映射

源 frontmatter：`name`、`description`、`tools: Read, Write, …`、`model: inherit|sonnet`。

| 目标 | 可写判定（tools 含 Write 或 Edit） | 模型 |
|---|---|---|
| Codex `sandbox_mode` | `workspace-write` / `read-only` | 不写，沿用会话默认 |
| OpenCode `permission` | 可写不加；只读 `edit: deny` | 不写 |
| Antigravity `model` | 无只读开关 | `sonnet → flash`，其余 `inherit` |
| Pi `tools` | `read, bash, edit, write, grep, find, ls` / 去掉 `edit, write` | 不写，继承会话 |

目前只有 judge 是只读角色；checker 要写 `chapters/reviews/chNNNN.check.json`。

## 各运行时核实要点与来源

- **Cursor**（cursor.com/docs/subagents, /skills, /rules, /hooks, /reference/third-party-hooks）：子智能体目录含 `.cursor/agents/`、`.claude/agents/`、`.codex/agents/`；frontmatter `description`、`model`（默认 inherit）、`readonly`、`is_background`；skill 读 `.agents/skills/`、`.cursor/skills/`，兼容 `.claude/skills/`、`.codex/skills/`；支持 AGENTS.md；`.cursor/hooks.json` 之外还会合并 `.claude/settings.json` 的 Claude Code 钩子（PostToolUse → postToolUse）。编辑器与 CLI 同一套。
- **Codex**（learn.chatgpt.com/docs/agent-configuration/subagents, /docs/build-skills）：`multi_agent` 已 stable；自定义角色 `.codex/agents/<name>.toml`，必填 `name`、`description`、`developer_instructions`，可选 `model`、`sandbox_mode`；按 `name` 识别；skill 读 `.agents/skills/`，`$skill-name` 显式调用。
- **OpenCode**（opencode.ai/docs/agents, /skills, /rules, /plugins）：`.opencode/agents/<name>.md`，`description` 必填，`mode: subagent`，`tools` 已弃用改 `permission`；`@name` 或按描述自动派发，`permission.task` 控制可派发对象；skill 读 `.opencode/skills/`、`.claude/skills/`、`.agents/skills/`，只能经 `skill` 工具调用；AGENTS.md 自动读取；钩子只能写 JS/TS 插件。
- **Antigravity**（antigravity.google/docs/subagents, /skills, /rules, /hooks, /plugins）：`.agents/agents/<name>.md`，frontmatter `name`、`description`、`model: inherit|flash|pro`、`subagent`、`mainAgent`；`invoke_subagent` 一次可传多个 spec 并行；skill 读 `.agents/skills/`，`/<skill-name>`；AGENTS.md / GEMINI.md 作为 always_on 规则；`.agents/hooks.json` 的 PostToolUse 只能返回 `{}`，无法把 lint 结果回馈给模型；插件 `plugin.json` 只允许 `name` 与 `description`。子智能体页只标注 2.0 与 CLI，IDE 是否可用未确认。`/agents` 面板只列 `mainAgent: true` 的角色，生成的角色都是 `mainAgent: false`，不出现在面板里属正常，主会话照样能用 `invoke_subagent` 派发（CLI 1.2.15 实测主会话能识别全部七个子智能体，尚未实际派发）。
- **Pi**（github.com/badlogic/pi-mono `packages/coding-agent/docs/`，包已改名 `@earendil-works/pi-coding-agent`）：skill 读 `.pi/skills/`、`.agents/skills/`、`~/.pi/agent/skills/`，`/skill:name`；子智能体不内置，官方示例扩展 `examples/extensions/subagent` 读 `.pi/agents/*.md`（`name`、`description`、`tools`、`model`），默认 `agentScope: user`，要改成 `project` 或 `both`；AGENTS.md 与 CLAUDE.md 都读；钩子只能写 TS 扩展。

## 未实测

生成物的格式按上述文档写，但没有在 Cursor、OpenCode、Antigravity、Pi 里真正派发过一轮。
Cursor 读取 `.claude/agents/` 时，源里的 `model: sonnet` 不是 Cursor 的模型 ID，行为未知；
OpenCode 与 Cursor 会同时看到 `.claude/skills/` 与 `.agents/skills/` 两份同名 skill，是否告警未知。
只在一个运行时里用时，用 `--runtime <name>` 只生成那一套可避开这两点。
