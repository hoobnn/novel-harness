---
name: novel-sync
description: 接纳用户对 chapters/final 的手动修改：检测被改动的章节，重新抽取事实并重建账本与索引。
---

1. `python3 tools/novel.py sync`。为空则报告「无手改章节」并结束。
2. 对每个被改章节 N：派 `ledger` 重新抽取并覆盖 `chapters/facts/chNNNN.json`（prompt 说明这是手改后的重抽，需与前后章事实接续），`validate-facts N` 通过后 `python3 tools/novel.py commit N --force`。commit 会从全部 facts 重放账本并重建该章索引，不会重复追加。
3. 若被改章节属于已做弧级评审的弧，提醒用户该弧摘要可能过时，可用 `/novel-harness:novel-arc-review vXaY` 重做。
4. 汇报：重抽的章节、事实变化要点（线程动作、知识、状态变化的增减）。

若手改推翻了后文依赖的关键事实（死者复活、知情者变不知情），后续章节的 facts 不会自动改，提醒用户确认是否需要返工后文。
