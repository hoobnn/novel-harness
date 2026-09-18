---
name: novel-init
description: 从一句话需求（或一份需求文件）初始化整本书的基础设定：前提、世界规则、日历、人物卡、故事线、指南针、首弧大纲、文风标准。完成后停下让用户审阅。
---

用户需求：$ARGUMENTS（若是文件路径，先读文件全文作为需求）。

1. 运行初始化：执行 [init.sh](./scripts/init.sh)（或 `python3 tools/novel.py init`），在当前工作区建立目录骨架与环境，然后 `python3 tools/novel.py status`。若 `foundation_missing` 为空且 `phase != init`，告诉用户已存在设定，询问是否覆盖，未确认不要继续。
2. 若用户需求里没有说明题材、目标体量（章数或卷数）、目标读者、文风参照，先问清这四点再派发；用户明确说「你定」就按题材惯例定并在报告里写明。
3. 派 `architect` 子智能体做初始规划，prompt 包含：用户原话、四点澄清结果、`docs/schemas.md` 路径、完成判据（`status.foundation_missing` 为空）。
4. 校验：`python3 tools/novel.py status` 的 `foundation_missing` 必须为空；`python3 tools/novel.py locate 1` 必须返回条目；`threads/registry.json` 至少一条 `main`。不通过就带错误重派，最多 2 次。
5. `python3 tools/novel.py set-phase foundation`。
6. 向用户汇报：书名与一句话前提、主要人物与各自的 want/need、卷 1 各弧目标、预登记的故事线与兑现窗口、文风标准要点、架构师标记的待确认问题。明确告诉用户：**审阅并修改 `bible/` `outline/` `threads/` 后，说「开始写」或运行 `/novel-next`**；开始写之前会 `set-phase writing`。
