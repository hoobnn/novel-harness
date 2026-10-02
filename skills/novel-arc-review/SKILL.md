---
name: novel-arc-review
description: 手动触发弧级或卷级评审（通常由路由自动触发；用于补做或重做）。参数形如 v1a2 或 v1。
---

参数：$ARGUMENTS（`vXaY` 弧级，`vX` 卷级；为空则取 `status.route` 中的评审目标）。

- 弧级：用 `python3 tools/novel.py locate` 找出该弧章节区间（区间内所有章都必须已提交），派 `editor` 做弧级评审，产出 `summaries/arcs/vXaY.json`；校验文件存在且含 summary / character_snapshots / style_rules，然后 `python3 tools/novel.py review-done vXaY`。
- 卷级：派 `editor` 做卷级评审，产出 `summaries/volumes/vX.json`，然后 `review-done vX`。
- 汇报：摘要要点、入队返工的章节及理由、提炼出的风格规则、open_questions；若 gate 为 per-arc，等用户确认后再继续 `/novel-harness:novel-next`。
