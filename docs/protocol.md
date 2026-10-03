# novel-harness 调度协议

主会话（你）是**确定性引擎**：读事实、查路由、派发子智能体、校验产物、推进状态。你自己不写正文、不做文学判断、不手改账本。所有需要判断力的工作都派给七个角色（architect / planner / writer / checker / editor / ledger / judge），所有能用代码判定的事情都交给工作区里的 `tools/novel.py`。

角色名：Claude Code 以插件方式安装时带前缀，如 `novel-harness:writer`；其他运行时（standalone 生成的定义）用裸名 `writer`。下文路由表统一写裸名。

数据契约唯一口径：`docs/schemas.md`。改任何文件格式前先读它。本文件与 `docs/schemas.md`、`tools/novel.py` 同版本分发，`python3 tools/novel.py upgrade` 一起刷新。

## 每轮循环

1. `python3 tools/novel.py status` → 读取 `route.action`。
2. 按下表派发。派发时把章节号、输入文件路径、输出文件路径、完成判据写进给子智能体的 prompt。
3. 子智能体返回后，用工具校验产物（见「完成判据」列），不通过就带着错误信息重派同一角色，最多 2 次。校验通过后记一步 `novel.py checkpoint add <章> <角色>`，会话中断时靠它判断续跑位置。
4. 再跑一次 `status`，直到命中闸门或 `done`。

| route.action | 派给 | 输入 | 产物 | 完成判据 |
|---|---|---|---|---|
| `architect:foundation` | architect | 用户需求 + `status.foundation_missing` | bible/、outline/、threads/registry.json | `status.foundation_missing` 为空；然后**必须停下让用户审阅**，用户确认后 `set-phase writing` |
| `architect:expand-arc` | architect | route 里的 volume/arc/goal | `outline/volumes.json` 该弧 `chapters` 填满 | `locate <next_chapter>` 返回条目 |
| `architect:new-volume` / `finale-check` | architect | 卷摘要、指南针、线程台账 | 追加新卷或宣告收官/完结 | 同上；完结时 `set-phase complete` |
| `planner` | planner | `context N --for planner` | `chapters/plans/chNNNN.md` | 文件存在且含「场景节拍表」「线程预算」「契约」三节 |
| `writer` | writer | `context N --for writer` | `chapters/drafts/chNNNN.md` | `lint N` 的 `issues` 为空（warnings 允许） |
| `checker+editor` | checker 与 editor **并行**派发，prompt 里写明 `route.round` | `context N --for checker/editor` | `chapters/reviews/chNNNN.check.json` 与 `chapters/reviews/chNNNN.json` | 两个文件都存在且 `verdict` 合法。checker 的 findings 由 `novel.py` 计入 verdict，不要手工合并进 review |
| `next-round` | 你自己执行 | — | `novel.py next-round N`：把本轮 review、check 与被评审的稿子归档为 `chNNNN.rK.*` | 输出含 `archived_round`，路由变为 `writer:revise` |
| `writer:revise` | writer（修订模式） | `route.review` 与 `route.check` 指向的归档评审 + 草稿 | 覆盖 `chapters/drafts/chNNNN.md` | `lint N` 的 `issues` 为空；草稿改动后路由自动进入下一轮 `checker+editor` |
| `finalize` | 你自己执行 | — | `novel.py finalize N` | 定稿文件存在 |
| `ledger` | ledger | 定稿 + 计划 | `chapters/facts/chNNNN.json` | `validate-facts N` 输出 OK |
| `commit` | 你自己执行 | — | `novel.py commit N` | 输出含 `committed`；检查 `flags` |
| `editor:arc-review` | editor（弧级模式） | route 里的章节区间 | `summaries/arcs/vXaY.json` + 需返工章节 `queue-revision` | 文件存在后 `review-done vXaY` |
| `editor:volume-review` | editor（卷级模式） | 本卷弧摘要 | `summaries/volumes/vX.json` | `review-done vX` |
| `revise` | editor 定范围 → writer 修订 → ledger 重抽 → `commit N --force` | `pending_revisions[0]` | 定稿与事实更新 | 队列弹出 |
| `steer` | 见「用户干预」 | `steer_queue[0]` | — | `steer pop` |

评审轮次由 `novel.py` 按归档文件数推出（`route.round`），不要手删 review，也不要让 editor 自己数轮次。想确认修订是否真的更好（用户要求，或第 2 轮分数不升反降）时，可派 judge 盲比 `chapters/reviews/chNNNN.r1.draft.md` 与当前草稿，结论写进返回报告，不改变路由。最多修订一次：第 2 轮评审仍是 `polish` 就直接 finalize，把遗留问题写进 facts 的 `outline_feedback`；仍是 `rewrite` 则 `route` 返回 `blocked`，停下问用户。

## 闸门（人工检查点）

`progress.gate`：
- `per-arc`（默认）：弧级评审完成后停下，把弧摘要和评审结论给用户看，用户说继续才展开下一弧。
- `per-chapter`：每章 commit 后停下。
- `auto`：只在基础设定完成、卷结束、完结、修订 2 轮仍 rewrite 时停下。

用户说「写到第 N 章」：忽略闸门直到 `last_committed >= N`，然后停下。

## 硬约束

- `ledger/`、`state/`、`index/` 只由 `novel.py` 写入。任何 Agent 都不得手改。账本是 `chapters/facts/` 的派生视图：`commit` 校验并给 facts 盖章后整体重放落盘，`novel.py rebuild` 随时可从 facts 重算；要改事实就改 facts 再 `commit N --force`。
- `threads/registry.json` 是 architect 的线程声明（新增、改承诺与兑现窗口、搁置）；线程运行态（是否落地、推进记录、停滞）看 `novel.py threads` 或 `ledger/threads.json`。
- 正文只出现在 `chapters/drafts` 与 `chapters/final`，由 writer 直接写文件。Agent 在聊天里输出正文不算完成；主会话不得从聊天消息里截取、拼接正文再落盘，writer 返回了正文却没写文件就重派。草稿里只能有章标题和正文：分割线、写作报告、字数统计会被 `lint` 拦下。
- 子智能体之间不共享上下文，一切靠文件。给子智能体的 prompt 必须包含：章节号、要读的文件、要写的文件、完成判据、不要做什么。
- 不把整本书塞进任何一个上下文。需要前文时用 `novel.py context / search / recall / timeline`。
- `bible/` 是权威设定，写作期只有 architect（经用户干预授权）可以修改；发现设定冲突先记到 `outline_feedback`，不要顺手改设定。
- commit 后 `git add -A && git commit -m "ch0012 <标题>"`。提交信息是否带 AI 署名按用户偏好；不知道时首次提交前问一次并记住。

## 用户干预（`novel-steer` skill 或用户直接说）

先 `novel.py steer add "<原话>"`，然后分诊，只做原话要求的事：
1. 文风或偏好类（「多用短句」「主角别太圣母」）→ 追加到 `bible/style/user-rules.md`，`steer pop`。
2. 后续走向类（「感情线提前」「加个反派」）→ 派 architect 增量修改大纲/线程/人物卡，不动已提交章节。
3. 已写内容返工类（「第 4 章重写」「把 X 改成女性」）→ 派 editor 圈定**最小充分章节集合**并逐个 `queue-revision`，走 `revise` 路由。
4. 控制类（「写到第 20 章」「停」「gate auto」）→ 直接执行。

## 预览台（`novel.py serve`）

用户可以在本地网页里查看进度、编辑产物、写批注。主会话需要知道的边界：
- 网页只能改 `bible/`、`outline/`、`threads/`、`chapters/plans|drafts|final`；评审、事实、账本、状态只读。保存时会做 sha 冲突检查，每次保存记一行 `state/decisions.jsonl`（`kind=studio-edit`）。网页写入不经过钩子，所以派发前仍以 `lint` / `status` 为准。
- 用户改了已提交章节的定稿，`status.unsynced` 会列出来，按 `novel-sync` 处理。用户改了 `bible/` 或大纲，视同用户授权的设定变更，不要改回去。
- 批注存在 `state/comments.json`。未处理批注会自动注入对应章节的 planner / writer / checker / editor 上下文包（「用户批注」段）。角色照批注改完后，主会话 `novel.py comment resolve <id> "怎么处理的"` 关闭它。
- 用户在网页上把批注「交给 Agent」，或者直接写干预，都会进 `steer_queue`；带 `comment` 字段的干预处理完，除了 `steer pop` 还要 `comment resolve <该 id>`。已提交章节的批注只有走这条路才会触发返工。
- `status.comments_open` 是未处理批注数。闸门停下汇报时，有未处理批注要一并提醒。

## 模型与成本

- 创作角色（architect / planner / writer / editor / judge）用主会话模型；抽取与核对角色（ledger / checker）用 sonnet。可在角色定义文件（插件 `agents/*.md`，standalone 为工作区 `.claude/agents/*.md`）的 `model` 字段调整。
- 上下文包已经把前情、账本、检索结果装配好，子智能体不要再全量读 `chapters/final`；确需回读时只读 1 到 2 章。

## 子智能体派发与运行环境

角色定义由 `novel.py init --standalone` 按运行时生成（Claude Code 插件模式除外），各家的目录、字段与派发写法见 `docs/runtimes.md`。要点：
- **Claude Code**：Agent 工具派发，插件模式 `novel-harness:<role>`，standalone 模式 `<role>`。
- **Cursor**：原生读取 `.claude/agents/`，`/writer` 或自然语言点名，一条消息里多次派发即并行。
- **Codex**：`.codex/agents/<role>.toml`，指令里点名角色即派发，`checker+editor` 在同一条指令里点名两个角色即并行。
- **OpenCode**：`.opencode/agents/<role>.md`，`@writer` 点名或按描述自动派发。
- **Antigravity**：`.agents/agents/<role>.md`，`invoke_subagent` 的 `TypeName` 填角色名，一次传多个 spec 即并行。
- **Pi**：需装官方示例扩展 `subagent` 并把 `agentScope` 设为 `project`，读 `.pi/agents/<role>.md`；用自然语言点名。
- **没有子智能体机制的运行时**：由主会话按角色文件逐个扮演，但产物、校验与状态推进规则不变。

## 常用命令

```bash
python3 tools/novel.py status                 # 进度 + 路由
python3 tools/novel.py context 12 --for writer
python3 tools/novel.py search "铁匠铺" --before 12
python3 tools/novel.py recall --entity 老周
python3 tools/novel.py timeline --entity 林越
python3 tools/novel.py threads --stale
python3 tools/novel.py check 12 / lint 12 / stylestat
python3 tools/novel.py gate per-chapter
python3 tools/novel.py checkpoint add 12 writer "草稿 3600 字"   # 子智能体返回并校验通过后记一步
python3 tools/novel.py next-round 12          # 评审要求修订时，归档本轮评审与被评审的稿子
python3 tools/novel.py rebuild                # 从已提交 facts 重放出 ledger/（升级后跑一次）
python3 tools/novel.py checkpoint list 12
python3 tools/novel.py serve --open           # 本地 Web 预览台（默认 127.0.0.1:8765）
python3 tools/novel.py comment list / resolve c0003 "已改"
python3 <插件目录>/tools/novel.py upgrade   # 升级 harness 后刷新工作区的 novel.py / 钩子 / 契约
```
