#!/usr/bin/env bash
# Antigravity PostToolUse hook：章节草稿/定稿写入后自动 lint；事实文件写入后自动校验。
set -u
input=$(cat)
plugin_root=$(cd "$(dirname "$0")/../.." && pwd)

eval "$(printf '%s' "$input" | python3 -c '
import json, sys
from pathlib import Path

try:
    d = json.load(sys.stdin)
    tool_call = d.get("toolCall", {})
    args = tool_call.get("args", {})
    path_str = args.get("TargetFile", "") or d.get("tool_input", {}).get("file_path", "")
except Exception:
    path_str = ""

if not path_str:
    print("TARGET_PATH=\"\"")
    sys.exit(0)

p = Path(path_str).resolve()
print(f"TARGET_PATH=\"{p}\"")

novel_root = ""
for parent in [p] + list(p.parents):
    if (parent / "state").exists() or (parent / "bible").exists() or (parent / "chapters").exists():
        novel_root = str(parent)
        break

if not novel_root:
    novel_root = str(Path.cwd())

print(f"NOVEL_ROOT=\"{novel_root}\"")
' 2>/dev/null)"

if [ -z "${TARGET_PATH:-}" ]; then
  printf '{}'
  exit 0
fi

novel_cmd="python3 $plugin_root/tools/novel.py"
if [ -f "${NOVEL_ROOT:-}/tools/novel.py" ]; then
  novel_cmd="python3 $NOVEL_ROOT/tools/novel.py"
fi

case "$TARGET_PATH" in
  */chapters/drafts/ch[0-9][0-9][0-9][0-9].md|*/chapters/final/ch[0-9][0-9][0-9][0-9].md)
    out=$(NOVEL_ROOT="${NOVEL_ROOT:-}" $novel_cmd lint "$TARGET_PATH" 2>&1)
    issues=$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("\n".join(d.get("issues",[])))' 2>/dev/null)
    if [ -n "$issues" ]; then
      printf 'novel lint 发现必须修复的问题（%s）：\n%s\n' "$(basename "$TARGET_PATH")" "$issues" >&2
      exit 2
    fi
    ;;
  */chapters/facts/ch[0-9][0-9][0-9][0-9].json)
    n=$(basename "$TARGET_PATH" .json | sed 's/^ch0*//')
    out=$(NOVEL_ROOT="${NOVEL_ROOT:-}" $novel_cmd validate-facts "$n" 2>&1)
    if [ "$out" != "OK" ]; then
      printf 'validate-facts %s 未通过：\n%s\n' "$n" "$out" >&2
      exit 2
    fi
    ;;
esac

printf '{}'
exit 0
