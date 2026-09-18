---
name: novel-steer
description: 注入用户干预（改文风、改后续走向、返工已写章节、控制类指令），按 CLAUDE.md「用户干预」分诊执行。
---

用户原话：$ARGUMENTS

1. `python3 tools/novel.py steer add "<原话>"`。
2. 按 CLAUDE.md「用户干预」四类分诊，只做原话要求的事。分诊结果和理由写入 `state/decisions.jsonl`（一行 JSON：at / kind=steer / text / triage / actions）。
3. 执行：
   - 偏好类：追加到 `bible/style/user-rules.md`。
   - 走向类：派 `architect` 增量修改，prompt 里附原话与「不动已提交章节」的约束；完成后核对 `status`。
   - 返工类：派 `editor` 圈定最小充分章节集合并 `queue-revision`；然后走 `revise` 路由（editor 定范围 → writer 修订 → ledger 重抽 → `commit N --force`）。
   - 控制类：直接执行 `gate` / `set-phase` / 写到第 N 章。
4. `python3 tools/novel.py steer pop`。
5. 汇报做了什么、改了哪些文件、影响到的章节。
