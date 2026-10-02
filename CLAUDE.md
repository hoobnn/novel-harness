# novel-harness（插件仓库）

这是 novel-harness 的**插件源码仓库**，不是小说工作区：这里没有 `bible/`、`chapters/`、`state/`。小说在用户自己的目录里，由 `python3 tools/novel.py init` 脚手架生成。运行期的调度协议在 `docs/protocol.md`，数据契约在 `docs/schemas.md`，两者随 `tools/novel.py` 一起复制进每个工作区。

## 布局

```
agents/                    七个角色（插件自动发现，名字带前缀 novel-harness:）
skills/                    六个入口 skill（/novel-harness:novel-*）；novel-init/scripts/init.sh 负责三种安装方式的自举
hooks/hooks.json           Claude Code 插件钩子 → tools/hooks/post_write.sh
tools/novel.py             事实层：单文件、仅标准库；init 时复制进工作区
tools/hooks/post_write.sh  写入后校验钩子（Claude Code / Antigravity 共用，根目录从被写文件向上找）
docs/protocol.md           调度协议（随版本分发）
docs/schemas.md            数据契约（随版本分发）
templates/workspace/       新工作区种子：CLAUDE.md、文风标准、.gitignore（只在 init 播种，之后归用户）
.claude-plugin/            plugin.json + marketplace.json（单插件仓库自带市场）
plugin.json hooks.json rules/ .agents/   Antigravity 侧的插件表面
tests/smoke_test.py        冒烟测试：脚手架、路由、钩子两种载荷
```

## 改动规则

- 改任何文件格式先读 `docs/schemas.md`；改路由先读 `docs/protocol.md` 与 `novel.py` 的 `route()`。
- 随版本分发进工作区的文件清单是 `novel.py` 里的 `VENDORED`；新增这类文件要同时加进去。
- 三种安装方式：Claude Code 插件（自带市场）、`claude --plugin-dir`、`npx skills add`（只装 skill，`init.sh` 克隆仓库到 `~/.cache/novel-harness/src` 后 standalone 初始化）。改 `init.sh` 或 `upgrade` 时三条路径都要过冒烟测试。
- 发版改四处版本号：`novel.py` 的 `__version__`、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、根 `plugin.json`。
- 验证：`python3 tests/smoke_test.py`；`claude plugin validate . --strict`（市场清单）、`claude plugin validate skills --strict`、`claude plugin validate agents --strict`；`claude plugin validate .claude-plugin/plugin.json` 会有且只有一条警告：根目录 CLAUDE.md 不会作为插件上下文分发。这是有意的，它只是本仓库的贡献者指南，运行期协议在 `docs/protocol.md`。本地试用：`claude --plugin-dir .`，再到一个空目录里 `/novel-harness:novel-init …`。
- 提交信息遵循 commitlint（gitmoji + Conventional Commits），带 Co-Authored-By 署名。
