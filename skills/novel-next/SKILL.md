---
name: novel-next
description: 推进创作：按 status 路由循环派发 planner / writer / checker / editor / ledger 并提交，直到命中闸门。可带参数「N」表示写到第 N 章为止。
---

参数：$ARGUMENTS（可为空；数字 N 表示写到第 N 章后停下，忽略 gate）。

严格按 `CLAUDE.md` 的「每轮循环」执行：

1. 若 `phase == foundation`，先确认用户已审阅设定（本会话里用户说过「开始写」即可），执行 `python3 tools/novel.py set-phase writing`。
2. 循环：`python3 tools/novel.py status` → 按路由表派发 → 校验产物 → 再 `status`。
3. `checker` 与 `editor` 用一条消息并行派发；editor 的 prompt 里说明 check.json 会由 checker 生成，若 editor 先完成而 check.json 不存在，主会话在 checker 返回后把 findings 合并进 review 的 consistency 维度（critical 存在时 verdict 升为 rewrite）。
4. commit 后按 CLAUDE.md 做 git 提交（首次提交前先问用户是否要 AI 署名，并把答案记入记忆）。
5. 停下的条件：命中 gate；参数 N 已达到；`route.action` 为 `architect:foundation`（设定被删）、`done`；修订 2 轮仍 rewrite；任何角色连续 2 次产物校验失败。
6. 停下时汇报：本次提交了哪些章（章号、标题、字数）、评审结论分布、线程台账里的 stale 与 overdue、下一步路由是什么、需要用户决定什么。不贴正文。
