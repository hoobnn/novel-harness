# novel-harness

> 在 Claude Code 与 Google Antigravity 里跑的长篇小说创作 Agent 团队。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/deps-stdlib%20only-green.svg)](tools/novel.py)

写到第 80 章时，模型早已不记得第 12 章那把匕首给了谁、老周到底知不知道主角的身份、
三卷前埋的伏笔有没有兑现。novel-harness 的答案是：**不靠模型记忆，靠账本**。

## 设计原则：事实层确定，语义层自主

| | 事实层 | 语义层 |
|---|---|---|
| **谁负责** | `tools/novel.py`（纯 Python 标准库） | `agents/` 下的七个角色 |
| **做什么** | 进度路由、时间线先后、线程到期、知识账本、文体统计、事实校验 | 规划、写作、核对、评审、抽取 |
| **判定方式** | 代码判定，结果唯一 | judgement，允许分歧 |

主会话只做调度：读事实 → 查路由 → 派发子智能体 → 校验产物 → 推进状态。
它不写正文、不做文学判断、不手改账本。

## 快速开始

需要 Python 3.10+（仅标准库，无需 `pip install`）和 Claude Code 或 Antigravity。

```bash
git clone https://github.com/hoobnn/novel-harness.git
cd novel-harness
python3 tools/novel.py init          # 初始化状态与索引（幂等）
```

然后在 Claude Code 里用 skill 驱动：

```
/novel-init 写一部东方玄幻长篇，主角从边陲小城起步，目标 200 章
```

基础设定生成后**会停下来等你审阅** `bible/` `outline/` `threads/`，改到满意再继续：

```
/novel-next                      # 按闸门推进（默认每弧停一次）
/novel-next 20                   # 一路写到第 20 章
/novel-status                    # 进度、线程健康度、文体统计
/novel-steer 感情线提前到第 4 章  # 注入干预
/novel-sync                      # 手改了 chapters/final 之后重建账本
```

## 角色分工

| 角色 | 输入 | 产物 |
|---|---|---|
| **architect** | 需求 / 前情 / 线程台账 | `bible/` `outline/` `threads/` |
| **planner** | `context N --for planner` | `chapters/plans/chNNNN.md` |
| **writer** | 章节计划 + 上下文包 | `chapters/drafts/chNNNN.md` |
| **checker** | 草稿 + 账本 | `chapters/reviews/chNNNN.check.json` |
| **editor** | 草稿 + 检查结论 | `chapters/reviews/chNNNN.json`、弧/卷摘要 |
| **ledger** | 定稿 | `chapters/facts/chNNNN.json` |
| **judge** | 同一章的两个版本 | 盲比结论 |

创作角色（architect / planner / writer / editor / judge）用主会话模型；
抽取与核对角色（ledger / checker）用 sonnet，可在 `agents/*.md` 的 `model` 字段调整。

### 每章流水线

```
planner → writer → (checker ∥ editor) → 修订 ≤ 2 轮 → finalize → ledger → commit
```

- **弧末**：editor 弧级评审 + 弧摘要 + 角色快照 + 风格规则 → architect 展开下一弧
- **卷末**：卷摘要 → architect 追加新卷或宣告收官

闸门（`progress.gate`）控制在哪里停下等人：`per-arc`（默认）、`per-chapter`、`auto`。

## 事实层命令

```bash
python3 tools/novel.py status                    # 进度 + 下一步路由
python3 tools/novel.py context 12 --for writer   # 装配第 12 章上下文包
python3 tools/novel.py search "铁匠铺" --before 12 # 场景级全文检索
python3 tools/novel.py recall --entity 老周       # 召回某实体的全部账本
python3 tools/novel.py timeline --entity 林越     # 时间线查询
python3 tools/novel.py threads --stale           # 停滞与超期的故事线
python3 tools/novel.py check 12                  # 连续性检查
python3 tools/novel.py lint 12                   # 文体机械检查
python3 tools/novel.py stylestat                 # 全书文体统计
python3 tools/novel.py commit 12                 # 提交定稿并更新账本
```

完整子命令见 `python3 tools/novel.py --help`。

## 目录结构

```
agents/      七个角色的提示词（.claude/agents 与 .agents/agents 为符号链接）
skills/      六个工作流入口（novel-init / next / status / steer / sync / arc-review）
tools/       novel.py 事实层工具 + 写入后校验钩子
bible/       世界规则、日历、人物卡、文风标准 —— 权威设定
outline/     卷弧大纲与指南针
threads/     故事线注册表（承诺与兑现窗口）
chapters/    plans/ drafts/ reviews/ final/ facts/
ledger/      人物台账与关系图        ← 只由 novel.py 写入
state/       进度与路由状态          ← 只由 novel.py 写入
summaries/   章/弧/卷摘要            ← 只由 novel.py 写入
index/       SQLite FTS5 全文索引    ← 只由 novel.py 写入
docs/        schemas.md —— 数据契约唯一口径
```

## 相比原作的改进

参考并改进自 [voocel/ainovel-cli](https://github.com/voocel/ainovel-cli)，新增：

- **场景级全文检索** —— SQLite FTS5 + CJK bigram 分词，「老周」这类两字人名也能检索到
- **机械校验的时间线** —— 以「故事内第几天」计数，先后矛盾由代码报错
- **故事线注册表** —— 每条线带承诺与兑现窗口，超期自动进入 `--stale`
- **知识账本** —— 每个人物「此刻知道什么」的投影，杜绝角色提前知情
- **独立的 checker 与 ledger 角色** —— 核对与抽取和创作解耦
- **盲比评审** —— judge 匿名比对修订前后，判断改动是否真的更好

## 文档

- 数据契约：[`docs/schemas.md`](docs/schemas.md) —— 改任何文件格式前先读它
- 调度协议：[`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md) / [`GEMINI.md`](GEMINI.md)

## 许可协议

[MIT](LICENSE) © hoobnn
