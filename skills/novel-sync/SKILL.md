---
name: novel-sync
description: 接纳用户对 chapters/final 的手动修改：检测被改动的章节，重新抽取事实并重建账本与索引。
---

1. `python3 tools/novel.py sync`。为空则报告「无手改章节」并结束。
2. 对每个被改章节 N：删除 `chapters/facts/chNNNN.json` 里的 `committed_sha` 与 `committed_at`，派 `ledger` 重新抽取（prompt 说明这是手改后的重抽，需与前后章事实接续），`validate-facts N` 通过后 `python3 tools/novel.py commit N --force`。
3. 全部完成后 `python3 tools/novel.py reindex`。
4. 若被改章节属于已做弧级评审的弧，提醒用户该弧摘要可能过时，可用 `/novel-harness:novel-arc-review vXaY` 重做。
5. 汇报：重抽的章节、事实变化要点（线程动作、知识、状态变化的增减）。

注意：账本是追加式日志，`commit --force` 会追加新记录而不删除旧记录；时间线与知识账本里旧记录仍在，读者是「最新记录优先」。若手改推翻了关键事实，提醒用户在报告里确认。
