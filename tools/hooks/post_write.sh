#!/usr/bin/env bash
# PostToolUse 钩子（Claude Code 与 Antigravity 共用）：
#   章节草稿/定稿写入后自动 lint；事实文件写入后自动 validate-facts。
#   有问题时以 exit 2 + stderr 反馈给模型自行修复；无问题静默。
# 工作区根目录从被写入文件的路径向上查找 state/progress.json，与本脚本所在位置无关，
# 所以它既能放在插件目录里（${CLAUDE_PLUGIN_ROOT}/tools/hooks/），也能放在工作区 tools/hooks/ 里。
set -u
HOOK_INPUT=$(cat)
here=$(cd "$(dirname "$0")" && pwd)
eval "$(HOOK_INPUT="$HOOK_INPUT" HOOK_HERE="$here" python3 - <<'PY'
import json, os, shlex
from pathlib import Path
here = Path(os.environ["HOOK_HERE"])
try:
    d = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except Exception:
    d = {}
ti = d.get("tool_input") or {}                      # Claude Code: Write / Edit
args = (d.get("toolCall") or {}).get("args") or {}  # Antigravity: write_to_file / replace_file_content
target = ti.get("file_path") or args.get("TargetFile") or args.get("file_path") or ""
root = ""
if target:
    p = Path(target).expanduser().resolve()
    for parent in (p, *p.parents):
        if (parent / "state/progress.json").exists():
            root = str(parent)
            break
# 优先用工作区自带的 novel.py（与该工作区的数据契约同版本），否则用钩子所在 harness 的
cands = ([Path(root) / "tools/novel.py"] if root else []) + [here.parent / "novel.py"]
tool = next((str(c) for c in cands if c.exists()), "")
print("TARGET_PATH=" + shlex.quote(str(target)))
print("NOVEL_ROOT=" + shlex.quote(root))
print("NOVEL_PY=" + shlex.quote(tool))
PY
)"
if [ -z "${TARGET_PATH:-}" ] || [ -z "${NOVEL_ROOT:-}" ] || [ -z "${NOVEL_PY:-}" ]; then
  printf '{}'
  exit 0
fi
export NOVEL_ROOT
case "$TARGET_PATH" in
  */chapters/drafts/ch[0-9][0-9][0-9][0-9].md|*/chapters/final/ch[0-9][0-9][0-9][0-9].md)
    out=$(python3 "$NOVEL_PY" lint "$TARGET_PATH" 2>&1)
    issues=$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("\n".join(d.get("issues",[])))' 2>/dev/null)
    if [ -n "$issues" ]; then
      printf 'novel lint 发现必须修复的问题（%s）：\n%s\n' "$(basename "$TARGET_PATH")" "$issues" >&2
      exit 2
    fi
    ;;
  */chapters/facts/ch[0-9][0-9][0-9][0-9].json)
    n=$(basename "$TARGET_PATH" .json | sed 's/^ch0*//')
    out=$(python3 "$NOVEL_PY" validate-facts "$n" 2>&1)
    if [ "$out" != "OK" ]; then
      printf 'validate-facts %s 未通过：\n%s\n' "$n" "$out" >&2
      exit 2
    fi
    ;;
esac
printf '{}'
exit 0
