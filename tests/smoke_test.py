#!/usr/bin/env python3
"""novel-harness 冒烟测试（仅标准库）。

覆盖可分发模式的关键路径：
  1. 从插件目录 init 到一个空目录：骨架、随版本分发的文件、模板、settings、版本号
  2. 工作区内（含子目录）status 正常；插件目录自身不是工作区
  3. 钩子脚本放在插件目录里也能从被写文件反推工作区：Claude Code 与 Antigravity 两种载荷
  4. upgrade 刷新 vendored 文件并记录版本
  5. --standalone 把角色与 skill 复制进 .claude/
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
NOVEL = HARNESS / "tools/novel.py"
HOOK = HARNESS / "tools/hooks/post_write.sh"


def run(*args, cwd=None, env=None, stdin=None):
    e = {k: v for k, v in os.environ.items() if k != "NOVEL_ROOT"}
    if env:
        e.update(env)
    return subprocess.run(list(args), cwd=cwd, env=e, input=stdin, text=True, capture_output=True)


def check(cond, msg):
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok  {msg}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="novel-ws-"))
    try:
        ws = (tmp / "my-novel").resolve()   # macOS 的 /var 是 /private/var 的软链，先 resolve 再比较
        ws.mkdir()

        # 1. init
        r = run(sys.executable, str(NOVEL), "init", cwd=ws)
        check(r.returncode == 0, f"init 成功: {r.stdout.strip().splitlines()[0] if r.stdout else r.stderr}")
        for rel in ("state/progress.json", "tools/novel.py", "tools/hooks/post_write.sh", "docs/schemas.md", "docs/protocol.md",
                    "bible/style/voice.md", "bible/style/anti-ai-tone.md", "bible/style/user-rules.md", "bible/style/rules.json",
                    "CLAUDE.md", "AGENTS.md", ".gitignore", ".claude/settings.json", "chapters/drafts", "ledger/cast.json"):
            check((ws / rel).exists(), f"init 产出 {rel}")
        check(not (ws / "tools/novel.py").is_symlink(), "novel.py 是复制而不是软链")
        settings = json.loads((ws / ".claude/settings.json").read_text())
        check("hooks" not in settings and settings["permissions"]["allow"], "插件模式的 settings 只有权限白名单、没有钩子")
        prog = json.loads((ws / "state/progress.json").read_text())
        ver = run(sys.executable, str(NOVEL), "version").stdout.strip()
        check(prog.get("harness_version") == ver, f"progress 记录 harness_version={ver}")
        r2 = run(sys.executable, str(NOVEL), "init", cwd=ws)
        check(r2.returncode == 0 and "幂等" in r2.stdout, "init 幂等")

        # 已有 CLAUDE.md 时只追加
        ws2 = tmp / "existing"
        ws2.mkdir()
        (ws2 / "CLAUDE.md").write_text("# 我的项目\n", encoding="utf-8")
        run(sys.executable, str(NOVEL), "init", cwd=ws2)
        txt = (ws2 / "CLAUDE.md").read_text(encoding="utf-8")
        check(txt.startswith("# 我的项目") and "novel-harness:begin" in txt, "已有 CLAUDE.md 时追加带标记段落")
        run(sys.executable, str(NOVEL), "init", cwd=ws2)
        check((ws2 / "CLAUDE.md").read_text(encoding="utf-8").count("novel-harness:begin") == 1, "重复 init 不重复追加")

        # 2. status：工作区内任意子目录可用；插件目录不是工作区
        r = run(sys.executable, "tools/novel.py", "status", cwd=ws)
        check(r.returncode == 0 and json.loads(r.stdout)["route"]["action"] == "architect:foundation", "工作区 status 路由到 architect:foundation")
        r = run(sys.executable, str(ws / "tools/novel.py"), "status", cwd=ws / "chapters/drafts")
        check(r.returncode == 0 and json.loads(r.stdout)["harness"]["root"] == str(ws), "子目录里运行也能找到工作区根")
        r = run(sys.executable, str(NOVEL), "status", cwd=HARNESS)
        check(r.returncode != 0 and "不是小说工作区" in r.stderr, "插件目录自身不是工作区，status 明确报错")
        r = run(sys.executable, str(NOVEL), "init", cwd=HARNESS)
        check(r.returncode != 0 and "harness 本身" in (r.stderr + r.stdout), "插件目录里 init 被拒绝")

        # 3. 钩子：脚本在插件目录里，从被写文件反推工作区
        bad = ws / "chapters/drafts/ch0001.md"
        bad.write_text("# 第一章\n\n" + "某种程度上他沉默了。" * 3 + "\n", encoding="utf-8")
        payload_cc = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}})
        r = run("bash", str(HOOK), cwd=tmp, stdin=payload_cc)
        check(r.returncode == 2 and "novel lint" in r.stderr, "Claude Code 载荷：有 issue 时 exit 2")
        payload_agy = json.dumps({"toolCall": {"name": "write_to_file", "args": {"TargetFile": str(bad)}}})
        r = run("bash", str(HOOK), cwd=tmp, stdin=payload_agy)
        check(r.returncode == 2 and "novel lint" in r.stderr, "Antigravity 载荷：有 issue 时 exit 2")
        r = run("bash", str(HOOK), cwd=tmp, stdin=json.dumps({"tool_input": {"file_path": str(tmp / "unrelated.md")}}))
        check(r.returncode == 0, "工作区外的文件静默放行")
        r = run("bash", str(HOOK), cwd=tmp, stdin="not json")
        check(r.returncode == 0, "非 JSON 载荷静默放行")

        # 4. upgrade
        (ws / "docs/protocol.md").write_text("stale", encoding="utf-8")
        r = run(sys.executable, str(NOVEL), "upgrade", cwd=ws)
        check(r.returncode == 0 and (ws / "docs/protocol.md").read_text(encoding="utf-8") != "stale", "upgrade 刷新 vendored 文件")
        r = run(sys.executable, "tools/novel.py", "upgrade", cwd=ws)
        check(r.returncode != 0 and "不知道从哪里升级" in r.stderr, "工作区自身的 novel.py 无来源时拒绝 upgrade")

        # 5. standalone
        ws3 = tmp / "standalone"
        ws3.mkdir()
        r = run(sys.executable, str(NOVEL), "init", "--standalone", cwd=ws3)
        check(r.returncode == 0 and (ws3 / ".claude/agents/writer.md").exists() and (ws3 / ".claude/skills/novel-next/SKILL.md").exists(), "standalone 复制角色与 skill")
        settings = json.loads((ws3 / ".claude/settings.json").read_text())
        check("PostToolUse" in settings.get("hooks", {}), "standalone 写入钩子")
        print("ALL OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
