---
name: novel-status
description: 汇报创作进度、下一步路由、故事线健康度（停滞与超期）、全书文体统计、未同步的手改章节、未处理的预览台批注数（`comments_open`）。
---

运行 `python3 tools/novel.py status`、`python3 tools/novel.py threads --stale`、`python3 tools/novel.py stylestat`，用不超过 15 行汇报：已提交章数与总字数、当前卷弧位置、下一步路由与原因、gate、活跃/停滞/超期线程、文体统计里章均最高的两个句式模式与重复句数量、未同步的手改章节。有异常（大纲耗尽、设定缺失、pending_revisions 堆积）先说。
