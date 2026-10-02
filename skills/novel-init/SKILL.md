---
name: novel-init
description: 从一句话需求（或一份需求文件）初始化整本书的基础设定：前提、世界规则、日历、人物卡、故事线、指南针、首弧大纲、文风标准。完成后停下让用户审阅。
---

用户需求：$ARGUMENTS（若是文件路径，先读文件全文作为需求）。

1. 运行初始化：`bash "${CLAUDE_SKILL_DIR}/scripts/init.sh"`（在用户的小说目录里执行；它按顺序找 harness：插件目录 → 已有工作区 → 本地缓存（只装了 skill 时自动浅克隆仓库并以 standalone 模式初始化，角色复制进 `.claude/agents/`）。它会调用 `novel.py init`，把目录骨架、`tools/novel.py`、钩子、`docs/protocol.md`、`docs/schemas.md`、文风模板和工作区 `CLAUDE.md` 建好，幂等）。然后 `python3 tools/novel.py status`。若 `foundation_missing` 为空且 `phase != init`，告诉用户已存在设定，询问是否覆盖，未确认不要继续。若 init 报「这是 harness 本身的目录」，说明用户在插件仓库里运行，请他到自己的小说目录再来。
2. 若用户需求里没有说明题材、目标体量（章数或卷数）、目标读者、文风参照，先问清这四点再派发；用户明确说「你定」就按题材惯例定并在报告里写明。
3. 派 `architect` 子智能体（插件模式下名为 `novel-harness:architect`）做初始规划，prompt 包含：用户原话、四点澄清结果、工作区 `docs/schemas.md` 路径、完成判据（`status.foundation_missing` 为空）。
4. 校验：`python3 tools/novel.py status` 的 `foundation_missing` 必须为空；`python3 tools/novel.py locate 1` 必须返回条目；`threads/registry.json` 至少一条 `main`。不通过就带错误重派，最多 2 次。
5. `python3 tools/novel.py set-phase foundation`。
6. 向用户汇报：书名与一句话前提、主要人物与各自的 want/need、卷 1 各弧目标、预登记的故事线与兑现窗口、文风标准要点、架构师标记的待确认问题。明确告诉用户：**审阅并修改 `bible/` `outline/` `threads/` 后，说「开始写」或运行 `/novel-harness:novel-next`**；开始写之前会 `set-phase writing`。
