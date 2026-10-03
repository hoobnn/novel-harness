#!/usr/bin/env bash
# 在当前目录建立小说工作区。按三种安装方式依次找 harness 来源：
#   1. 本 skill 位于插件目录里（Claude Code 插件 / --plugin-dir）→ 用插件的 novel.py，角色与钩子由插件提供
#   2. 当前目录已是工作区（有 tools/novel.py）→ 幂等重跑
#   3. 只装了 skill（npx skills add hoobnn/novel-harness 等）→ 把仓库浅克隆到本地缓存，
#      以 --standalone 初始化：角色复制进 .claude/agents/，钩子写进 .claude/settings.json
# 环境变量：NOVEL_HARNESS_SRC 指定现成的 harness 目录（跳过克隆）；
#           NOVEL_HARNESS_REPO 覆盖克隆地址；XDG_CACHE_HOME 决定缓存位置。
set -u
here=$(cd "$(dirname "$0")" && pwd)
harness_root=$(cd "$here/../../.." && pwd)
if [ -f "$harness_root/tools/novel.py" ] && [ -d "$harness_root/agents" ]; then
  exec python3 "$harness_root/tools/novel.py" init "$@"
fi
if [ -f "tools/novel.py" ] && [ -f "state/progress.json" ]; then
  exec python3 tools/novel.py init "$@"
fi

src="${NOVEL_HARNESS_SRC:-}"
if [ -z "$src" ]; then
  src="${XDG_CACHE_HOME:-$HOME/.cache}/novel-harness/src"
  repo="${NOVEL_HARNESS_REPO:-https://github.com/hoobnn/novel-harness.git}"
  if [ ! -f "$src/tools/novel.py" ]; then
    command -v git >/dev/null 2>&1 || { echo "需要 git 来获取 novel-harness（或设置 NOVEL_HARNESS_SRC 指向已有的仓库目录）" >&2; exit 1; }
    mkdir -p "$(dirname "$src")"
    git clone --depth 1 -q "$repo" "$src" || { echo "克隆 $repo 失败" >&2; exit 1; }
  else
    git -C "$src" pull --ff-only -q >/dev/null 2>&1 || true   # 刷新失败不阻塞
  fi
fi
[ -f "$src/tools/novel.py" ] || { echo "$src 里没有 tools/novel.py" >&2; exit 1; }
echo "harness 来源：${src}（standalone 模式）"
exec python3 "$src/tools/novel.py" init --standalone "$@"
