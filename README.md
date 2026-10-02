# novel-harness

> 在 Claude Code 与 Google Antigravity 里跑的长篇小说创作 Agent 团队，以插件形式分发。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/deps-stdlib%20only-green.svg)](tools/novel.py)

写到第 80 章时，模型早已不记得第 12 章那把匕首给了谁、老周到底知不知道主角的身份、
三卷前埋的伏笔有没有兑现。novel-harness 的答案是：**不靠模型记忆，靠账本**。

## 设计原则：事实层确定，语义层自主

| | 事实层 | 语义层 |
|---|---|---|
| **谁负责** | `tools/novel.py`（纯 Python 标准库，单文件） | `agents/` 下的七个角色 |
| **做什么** | 进度路由、时间线先后、线程到期、知识账本、文体统计、事实校验 | 规划、写作、核对、评审、抽取 |
| **判定方式** | 代码判定，结果唯一 | judgement，允许分歧 |

主会话只做调度：读事实 → 查路由 → 派发子智能体 → 校验产物 → 推进状态。
它不写正文、不做文学判断、不手改账本。

## 两层结构：插件与工作区

```
novel-harness（本仓库，装一次）          my-novel/（每部小说一个目录，init 生成）
├── agents/      七个角色               ├── CLAUDE.md        指向 docs/protocol.md 的入口
├── skills/      六个 /novel-* 入口     ├── docs/protocol.md 调度协议   ┐ 随版本复制
├── hooks/       写入后校验钩子         ├── docs/schemas.md  数据契约   │ upgrade 刷新
├── tools/novel.py                      ├── tools/novel.py              ┘
├── docs/        protocol + schemas     ├── bible/ outline/ threads/   权威设定（architect 写）
└── templates/workspace/  种子文件      ├── chapters/ plans drafts reviews final facts
                                        └── ledger/ state/ summaries/ index/   只由 novel.py 写
```

工作区自带 `tools/novel.py` 与数据契约，和它的数据格式同版本；插件升级不会悄悄改变已有小说的行为，
需要时在工作区里运行 `python3 <插件目录>/tools/novel.py upgrade` 显式刷新。

## 安装

需要 Python 3.10+（仅标准库）。

**Claude Code（推荐）**：本仓库自带市场。

```
/plugin marketplace add hoobnn/novel-harness
/plugin install novel-harness@novel-harness
```

本地开发或试用：`git clone` 后 `claude --plugin-dir ./novel-harness`。

**不装插件**：在小说目录里 `python3 /path/to/novel-harness/tools/novel.py init --standalone`，
角色与 skill 会复制到该目录的 `.claude/` 下，slash 命令去掉 `novel-harness:` 前缀。

**Antigravity**：按 Antigravity 的插件方式加载本仓库（`plugin.json` / `hooks.json` / `rules/` / `.agents/`），
派发契约见 [`.agents/rules/antigravity.md`](.agents/rules/antigravity.md)。

## 快速开始

在一个空目录（你的小说目录）里打开 Claude Code：

```
/novel-harness:novel-init 写一部东方玄幻长篇，主角从边陲小城起步，目标 200 章
```

它会建立工作区并派架构师生成基础设定，然后**停下来等你审阅** `bible/` `outline/` `threads/`。改到满意再继续：

```
/novel-harness:novel-next                      # 按闸门推进（默认每弧停一次）
/novel-harness:novel-next 20                   # 一路写到第 20 章
/novel-harness:novel-status                    # 进度、线程健康度、文体统计
/novel-harness:novel-steer 感情线提前到第 4 章  # 注入干预
/novel-harness:novel-sync                      # 手改了 chapters/final 之后重建账本
/novel-harness:novel-arc-review v1a2           # 补做或重做弧级 / 卷级评审
```

工作区建议是 git 仓库：每章 commit 后主会话会 `git commit`。

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
插件模式下角色名带前缀，如 `novel-harness:writer`。

### 每章流水线

```
planner → writer → (checker ∥ editor) → 修订 ≤ 2 轮 → finalize → ledger → commit
```

- **弧末**：editor 弧级评审 + 弧摘要 + 角色快照 + 风格规则 → architect 展开下一弧
- **卷末**：卷摘要 → architect 追加新卷或宣告收官

闸门（`progress.gate`）控制在哪里停下等人：`per-arc`（默认）、`per-chapter`、`auto`。
完整调度协议见 [`docs/protocol.md`](docs/protocol.md)。

## 事实层命令

在工作区内任意目录运行：

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
python3 <插件目录>/tools/novel.py upgrade        # 刷新工作区的 novel.py / 钩子 / 契约
```

完整子命令见 `python3 tools/novel.py --help`。

## 写入后自动校验

插件注册了一个 `PostToolUse` 钩子：Agent 每次写 `chapters/drafts|final/chNNNN.md` 会自动跑 `lint`，
写 `chapters/facts/chNNNN.json` 会自动跑 `validate-facts`，不通过的问题直接回传给模型修复。
钩子从被写文件向上寻找工作区，所以插件装在哪里、小说放在哪里都不影响。

## 相比原作的改进

参考并改进自 [voocel/ainovel-cli](https://github.com/voocel/ainovel-cli)，新增：

- **场景级全文检索** —— SQLite FTS5 + CJK bigram 分词，「老周」这类两字人名也能检索到
- **机械校验的时间线** —— 以「故事内第几天」计数，先后矛盾由代码报错
- **故事线注册表** —— 每条线带承诺与兑现窗口，超期自动进入 `--stale`
- **知识账本** —— 每个人物「此刻知道什么」的投影，杜绝角色提前知情
- **独立的 checker 与 ledger 角色** —— 核对与抽取和创作解耦
- **盲比评审** —— judge 匿名比对修订前后，判断改动是否真的更好

## 开发

```bash
python3 tests/smoke_test.py                       # 脚手架、路由、钩子两种载荷、upgrade、standalone
claude plugin validate . --strict                 # 市场清单
claude plugin validate skills --strict            # skills
claude plugin validate agents --strict            # 角色
claude plugin validate .claude-plugin/plugin.json # 插件清单（根目录 CLAUDE.md 是贡献者指南，会有一条预期内的警告）
```

贡献者指南见 [`CLAUDE.md`](CLAUDE.md)，数据契约见 [`docs/schemas.md`](docs/schemas.md)。

## 许可协议

[MIT](LICENSE) © hoobnn
