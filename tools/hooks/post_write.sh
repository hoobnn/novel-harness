#!/usr/bin/env bash
# PostToolUse hook：章节草稿/定稿写入后自动 lint；事实文件写入后自动校验。
# 有问题时以 exit 2 + stderr 反馈给模型，无问题静默。
set -u
input=$(cat)
path=$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null)
[ -z "$path" ] && exit 0
root=$(cd "$(dirname "$0")/../.." && pwd)
case "$path" in
  */chapters/drafts/ch[0-9][0-9][0-9][0-9].md|*/chapters/final/ch[0-9][0-9][0-9][0-9].md)
    out=$(cd "$root" && python3 tools/novel.py lint "$path" 2>&1)
    issues=$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("\n".join(d.get("issues",[])))' 2>/dev/null)
    if [ -n "$issues" ]; then
      printf 'novel lint 发现必须修复的问题（%s）：\n%s\n' "$(basename "$path")" "$issues" >&2
      exit 2
    fi
    ;;
  */chapters/facts/ch[0-9][0-9][0-9][0-9].json)
    n=$(basename "$path" .json | sed 's/^ch0*//')
    out=$(cd "$root" && python3 tools/novel.py validate-facts "$n" 2>&1)
    if [ "$out" != "OK" ]; then
      printf 'validate-facts %s 未通过：\n%s\n' "$n" "$out" >&2
      exit 2
    fi
    ;;
esac
exit 0
