<!-- novel-harness:begin -->
# 长篇小说工作区（novel-harness）

本目录是一部长篇小说的工作区。主会话（你）是**确定性引擎**：读事实、查路由、派发子智能体、校验产物、推进状态；你自己不写正文、不做文学判断、不手改账本。

- **调度协议**：`docs/protocol.md`。每轮循环、路由表、闸门、修订上限、用户干预分诊都在里面，推进创作前先读它。
- **数据契约**：`docs/schemas.md`。改任何文件格式前先读它。
- **事实层工具**：`python3 tools/novel.py`（`status` / `context` / `lint` / `commit` …）。所有能用代码判定的事情都交给它。
- **用户偏好**：`bible/style/user-rules.md`，优先级最高。

硬约束：
- `ledger/`、`state/`、`summaries/chapters/`、`index/` 只由 `novel.py` 写入，任何 Agent 不得手改。
- 正文只出现在 `chapters/drafts` 与 `chapters/final`，在聊天里输出正文不算完成。
- `bible/` 是权威设定，写作期只有 architect（经用户授权）可以修改；发现设定冲突先记到 facts 的 `outline_feedback`，不要顺手改设定。
- 不把整本书塞进任何一个上下文；需要前文时用 `novel.py context / search / recall / timeline`。

入口（Claude Code 插件模式）：`/novel-harness:novel-init` `/novel-harness:novel-next` `/novel-harness:novel-status` `/novel-harness:novel-steer` `/novel-harness:novel-sync` `/novel-harness:novel-arc-review`。standalone 模式（角色与 skill 按运行时生成在本目录 `.claude/`、`.agents/` 等处）去掉 `novel-harness:` 前缀，如 `/novel-next`。
<!-- novel-harness:end -->
