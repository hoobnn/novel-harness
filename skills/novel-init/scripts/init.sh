#!/usr/bin/env bash
# 自动寻找 novel.py 并初始化当前工作区目录
set -u
plugin_root=$(cd "$(dirname "$0")/../../.." && pwd)
if [ -f "tools/novel.py" ]; then
  python3 tools/novel.py init "$@"
else
  python3 "$plugin_root/tools/novel.py" init "$@"
fi
