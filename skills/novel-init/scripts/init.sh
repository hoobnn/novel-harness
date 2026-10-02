#!/usr/bin/env bash
# 在当前目录建立小说工作区。优先用本 skill 所在 harness（插件目录）的 novel.py，
# 没有时退回工作区里已复制的 tools/novel.py（standalone 模式）。
set -u
here=$(cd "$(dirname "$0")" && pwd)
harness_root=$(cd "$here/../../.." && pwd)
if [ -f "$harness_root/tools/novel.py" ]; then
  exec python3 "$harness_root/tools/novel.py" init "$@"
fi
if [ -f "tools/novel.py" ]; then
  exec python3 tools/novel.py init "$@"
fi
echo "找不到 novel.py：请安装 novel-harness 插件，或在已 init 过的工作区里运行。" >&2
exit 1
