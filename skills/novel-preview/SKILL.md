---
name: novel-preview
description: 启动本地 Web 预览台：看创作进度与各章产物，在浏览器里编辑设定、大纲、计划、草稿、定稿，并对原文批注或提交干预。可带参数「端口」。
---

参数：$ARGUMENTS（可为空；数字表示端口，默认 8765，被占用时自动顺延）。

1. 在工作区里**后台**运行 `python3 tools/novel.py serve --open`（有端口参数时加 `--port <端口>`）。它是常驻进程，不要前台等待；`serve` 不被识别（旧工作区报 `invalid choice`）或缺 `tools/studio.html` 时，先跑 `python3 <插件目录>/tools/novel.py upgrade`。
2. 从输出里取 `novel studio: http://…` 那一行的地址告诉用户，并说明：
   - 页面每隔几秒自动刷新，Agent 写入的产物会实时出现；
   - 可编辑 `bible/`、`outline/`、`threads/`、`chapters/plans|drafts|final`，评审、事实、账本只读；
   - 选中正文可以批注。未处理批注会自动进入该章的上下文包；勾选「交给 Agent」或在干预框里写的话进入 steer 队列，下次 `novel-next` 先处理；
   - 改了已提交章节的定稿后，要跑 `novel-sync`。
3. 只绑定 127.0.0.1。用户要在手机或局域网里看时才加 `--host 0.0.0.0`，并提醒同一网络里的人都能改。
