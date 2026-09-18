# novel-harness

在 Claude Code 与 Google Antigravity (AGY) 里跑的长篇小说创作 Agent 团队。设计原则：**事实层确定，语义层自主**。能用代码判定的（进度路由、时间线先后、线程到期、知识账本、文体统计、事实校验）全部在 `tools/novel.py`；需要判断力的（规划、写作、核对、评审、抽取）交给 `.agents/agents/` / `.claude/agents/` 下的七个角色；主会话只做调度。

参考并改进自 [voocel/ainovel-cli](https://github.com/voocel/ainovel-cli)。相对它新增了：场景级全文检索（SQLite FTS5 trigram）、以「故事内第几天」计数并机械校验的时间线、带承诺与兑现窗口的故事线注册表、每个人物的知识账本与位置/状态投影、独立的连续性检查员与账本员角色、盲比评审。

## 快速开始

```
/novel-init 写一部东方玄幻长篇，主角从边陲小城起步，目标 200 章
# 审阅 bible/ outline/ threads/，改到满意
/novel-next            # 按闸门推进（默认每弧停一次）
/novel-next 20         # 写到第 20 章
/novel-status
/novel-steer 感情线提前到第 4 章
/novel-sync            # 手改了 chapters/final 之后
```

## 角色

| 角色 | 输入 | 产物 |
|---|---|---|
| architect | 需求 / 前情 / 线程台账 | bible/ outline/ threads/ |
| planner | `novel.py context N --for planner` | chapters/plans/chNNNN.md |
| writer | 计划 + 上下文包 | chapters/drafts/chNNNN.md |
| checker | 草稿 + 账本 | chapters/reviews/chNNNN.check.json |
| editor | 草稿 + 检查结论 | chapters/reviews/chNNNN.json；弧/卷摘要 |
| ledger | 定稿 | chapters/facts/chNNNN.json |
| judge | 两个版本 | 盲比结论 |

每章流程：planner → writer → (checker ∥ editor) → 修订 ≤ 2 轮 → finalize → ledger → commit。弧末：editor 弧级评审 + 摘要 + 角色快照 + 风格规则 → architect 展开下一弧。卷末：卷摘要 → architect 新卷或收官。

## 事实层命令

```
python3 tools/novel.py status            # 进度与下一步
python3 tools/novel.py context N --for writer
python3 tools/novel.py search "关键词" --before N
python3 tools/novel.py recall --entity 名字
python3 tools/novel.py timeline --entity 名字
python3 tools/novel.py threads --stale
python3 tools/novel.py check N | lint N | stylestat
python3 tools/novel.py commit N
```

数据契约见 `docs/schemas.md`，调度协议见 `CLAUDE.md` / `AGENTS.md`。
