#!/usr/bin/env python3
"""novel-harness 冒烟测试（仅标准库）。

覆盖可分发模式的关键路径：
  1. 从插件目录 init 到一个空目录：骨架、随版本分发的文件、模板、settings、版本号
  2. 工作区内（含子目录）status 正常；插件目录自身不是工作区
  3. 钩子脚本放在插件目录里也能从被写文件反推工作区：Claude Code 与 Antigravity 两种载荷
  4. upgrade 刷新 vendored 文件并记录版本
  5. --standalone 按运行时生成角色与 skill
  6. 只装 skill 时从缓存初始化与升级
  7. 0.1.0 工作区迁移：软链（断链 / 有效）、根目录角色副本、旧协议
  8. 预览台 serve：读写边界、冲突检查、本机 Host 校验、批注进入上下文包与干预队列
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
        for rel in ("state/progress.json", "tools/novel.py", "tools/hooks/post_write.sh", "tools/studio.html", "docs/schemas.md", "docs/protocol.md",
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

        # 5. standalone：按运行时生成角色与 skill
        ws3 = tmp / "standalone"
        ws3.mkdir()
        r = run(sys.executable, str(NOVEL), "init", "--standalone", cwd=ws3)
        check(r.returncode == 0 and (ws3 / ".claude/agents/writer.md").exists() and (ws3 / ".claude/skills/novel-next/SKILL.md").exists(), "standalone 复制 Claude 角色与 skill")
        check((ws3 / ".agents/skills/novel-next/SKILL.md").exists(), "standalone 把 skill 也放进 .agents/skills/（Cursor / Codex / OpenCode / Antigravity / Pi 共用）")
        settings = json.loads((ws3 / ".claude/settings.json").read_text())
        check("PostToolUse" in settings.get("hooks", {}), "standalone 写入钩子（Cursor 会合并同一份）")
        n_roles = len(list((HARNESS / "agents").glob("*.md")))
        for rt_dir in (".codex/agents", ".opencode/agents", ".agents/agents", ".pi/agents"):
            check(len(list((ws3 / rt_dir).iterdir())) == n_roles, f"standalone 生成 {rt_dir}/ 全部 {n_roles} 个角色")
        prog = json.loads((ws3 / "state/progress.json").read_text())
        check(prog.get("standalone_runtimes") == ["claude", "cursor", "codex", "opencode", "antigravity", "pi"], "progress 记录 standalone_runtimes")
        try:
            import tomllib
            w = tomllib.loads((ws3 / ".codex/agents/writer.toml").read_text(encoding="utf-8"))
            j = tomllib.loads((ws3 / ".codex/agents/judge.toml").read_text(encoding="utf-8"))
            check(w["name"] == "writer" and w["sandbox_mode"] == "workspace-write" and "你是写手" in w["developer_instructions"]
                  and j["sandbox_mode"] == "read-only", "Codex TOML 可解析：name / sandbox_mode / developer_instructions")
        except ModuleNotFoundError:
            print("skip tomllib (<3.11)")
        oc_judge = (ws3 / ".opencode/agents/judge.md").read_text(encoding="utf-8")
        oc_writer = (ws3 / ".opencode/agents/writer.md").read_text(encoding="utf-8")
        check(oc_judge.startswith("---\ndescription: ") and "mode: subagent" in oc_judge and "edit: deny" in oc_judge and "edit: deny" not in oc_writer,
              "OpenCode frontmatter：description / mode: subagent，只读角色 permission.edit: deny")
        ag_ledger = (ws3 / ".agents/agents/ledger.md").read_text(encoding="utf-8")
        ag_writer = (ws3 / ".agents/agents/writer.md").read_text(encoding="utf-8")
        check("name: ledger" in ag_ledger and "model: flash" in ag_ledger and "model: inherit" in ag_writer and "subagent: true" in ag_writer,
              "Antigravity frontmatter：model 映射 sonnet→flash / inherit，subagent: true")
        pi_judge = (ws3 / ".pi/agents/judge.md").read_text(encoding="utf-8")
        check("tools: read, bash, grep, find, ls" in pi_judge and "write" not in pi_judge.split("---")[1], "Pi frontmatter：只读角色不给 write/edit 工具")
        ws3b = tmp / "standalone-claude-only"
        ws3b.mkdir()
        r = run(sys.executable, str(NOVEL), "init", "--standalone", "--runtime", "claude", cwd=ws3b)
        check(r.returncode == 0 and (ws3b / ".claude/agents").is_dir() and not (ws3b / ".codex").exists() and not (ws3b / ".agents").exists(),
              "--runtime claude 只生成 Claude 的文件")
        (tmp / "x").mkdir()
        r = run(sys.executable, str(NOVEL), "init", "--standalone", "--runtime", "nope", cwd=tmp / "x")
        check(r.returncode != 0 and "未知运行时" in r.stderr, "--runtime 非法值报错")

        # 6. 只装了 skill（npx skills）：init.sh 找不到插件，回退到本地缓存并 --standalone
        ws4 = tmp / "skills-only"
        (ws4 / ".claude/skills").mkdir(parents=True)
        shutil.copytree(HARNESS / "skills/novel-init", ws4 / ".claude/skills/novel-init")
        (ws4 / "skills-lock.json").write_text("{}", encoding="utf-8")   # npx skills 的痕迹
        init_sh = ws4 / ".claude/skills/novel-init/scripts/init.sh"
        r = run("bash", str(init_sh), cwd=ws4, env={"NOVEL_HARNESS_SRC": str(HARNESS)})
        check(r.returncode == 0 and (ws4 / ".claude/agents/writer.md").exists() and (ws4 / "tools/novel.py").exists(),
              "skill 单独安装：NOVEL_HARNESS_SRC 指定来源，standalone 初始化带上角色")
        check((ws4 / ".claude/skills/novel-init/scripts/init.sh").exists() and not (ws4 / ".claude/skills/novel-next").exists(),
              "不覆盖 npx skills 已装的 .claude/skills/")
        cache_home = tmp / "cache"
        ws5 = tmp / "skills-only-clone"
        (ws5 / ".claude/skills").mkdir(parents=True)
        shutil.copytree(HARNESS / "skills/novel-init", ws5 / ".claude/skills/novel-init")
        r = run("bash", str(ws5 / ".claude/skills/novel-init/scripts/init.sh"), cwd=ws5,
                env={"XDG_CACHE_HOME": str(cache_home), "NOVEL_HARNESS_REPO": str(HARNESS)})
        check(r.returncode == 0 and (cache_home / "novel-harness/src/tools/novel.py").exists() and (ws5 / ".claude/agents/writer.md").exists(),
              f"skill 单独安装：无来源时浅克隆到缓存再初始化 ({r.stderr.strip()[:80] or 'ok'})")
        # 本地 clone 取的是 HEAD 而不是工作树，把当前 novel.py 同步进缓存与工作区，再测缓存回退
        for dst in (cache_home / "novel-harness/src/tools/novel.py", ws5 / "tools/novel.py"):
            shutil.copy2(HARNESS / "tools/novel.py", dst)
        (ws5 / "docs/protocol.md").write_text("stale", encoding="utf-8")
        r = run(sys.executable, "tools/novel.py", "upgrade", cwd=ws5, env={"XDG_CACHE_HOME": str(cache_home)})
        check(r.returncode == 0 and (ws5 / "docs/protocol.md").read_text(encoding="utf-8") != "stale" and ".claude/agents/writer.md" in r.stdout
              and ".codex/agents/writer.toml" in r.stdout,
              "工作区自身的 novel.py 能从缓存 upgrade 并按已有运行时目录重新生成角色")

        # 7. 0.1.0 工作区：tools/ 软链到（已卸载的）插件目录、根目录带角色副本与旧协议
        for ws6, live in ((tmp / "legacy-dangling", False), (tmp / "legacy-live", True)):
            ws6.mkdir()
            run(sys.executable, str(NOVEL), "init", cwd=ws6)
            prog = json.loads((ws6 / "state/progress.json").read_text())
            prog.pop("harness_version")
            (ws6 / "state/progress.json").write_text(json.dumps(prog), encoding="utf-8")
            old_plugin = tmp / f"old-plugin-{ws6.name}"
            (old_plugin / "tools/hooks").mkdir(parents=True)
            (old_plugin / "tools/novel.py").write_text("# old", encoding="utf-8")
            for rel in ("tools/novel.py", "tools/hooks"):
                shutil.rmtree(ws6 / rel) if (ws6 / rel).is_dir() else (ws6 / rel).unlink()
                (ws6 / rel).symlink_to(old_plugin / rel)
            if not live:
                shutil.rmtree(old_plugin)
            shutil.copytree(HARNESS / "agents", ws6 / "agents")
            for name in ("CLAUDE.md", "AGENTS.md"):
                (ws6 / name).unlink()
                (ws6 / name).write_text("# novel-harness：长篇小说创作 Agent 团队\n\n旧协议", encoding="utf-8")
            r = run(sys.executable, str(NOVEL), *(("upgrade",) if live else ("init", "--standalone", "--runtime", "antigravity")), cwd=ws6)
            check(r.returncode == 0 and not (ws6 / "tools/novel.py").is_symlink() and (ws6 / "tools/hooks/post_write.sh").exists()
                  and not (ws6 / "agents").exists(), f"0.1.0 工作区（{'软链有效，upgrade' if live else '断链，init'}）：拆软链、补齐工具、移除根目录角色副本")
            check(all("<!-- novel-harness:begin -->" in (ws6 / n).read_text(encoding="utf-8") and "旧协议" not in (ws6 / n).read_text(encoding="utf-8")
                      for n in ("CLAUDE.md", "AGENTS.md")), "0.1.0 工作区：旧协议副本换成工作区模板")
            check(json.loads((ws6 / "state/progress.json").read_text()).get("harness_version") == ver, "0.1.0 工作区：记录 harness_version")
            if live:
                check((old_plugin / "tools/novel.py").read_text(encoding="utf-8") == "# old", "升级不会顺着软链改写插件目录")
            else:
                check((ws6 / ".agents/agents/writer.md").exists(), "0.1.0 工作区 init --standalone 生成 Antigravity 角色")
        # 8. 预览台：在 init 出来的工作区里起服务（端口 0 取随机空闲端口）
        smoke_studio(ws)
        # 9. lint 新规则与评审轮次流转
        ws7 = tmp / "rounds"
        ws7.mkdir()
        run(sys.executable, str(NOVEL), "init", cwd=ws7)
        smoke_rounds(ws7)
        # 10. 账本由 facts 重放：重提不重复，上下文不看后文
        ws8 = tmp / "ledger"
        ws8.mkdir()
        run(sys.executable, str(NOVEL), "init", cwd=ws8)
        smoke_ledger(ws8)
        print("ALL OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def smoke_rounds(ws: Path) -> None:
    def nv(*args):
        return run(sys.executable, "tools/novel.py", *args, cwd=ws)

    def route():
        return json.loads(nv("status").stdout)["route"]

    for rel, text in (("bible/premise.md", "# 故事前提\n"), ("bible/world/rules.md", "# 规则\n"), ("bible/world/calendar.md", "# 日历\n"),
                      ("outline/compass.json", "{}"), ("threads/registry.json", '[{"id":"T01","title":"线","type":"main","status":"planned"}]'),
                      ("bible/characters.json", '[{"name":"林越","slug":"lin-yue","tier":"core"}]'),
                      ("outline/volumes.json", json.dumps([{"title": "卷", "arcs": [{"title": "弧", "chapters": [
                          {"title": "一", "characters": ["林越"], "target_words": [10, 60]}, {"title": "二"}]}]}], ensure_ascii=False)),
                      ("chapters/plans/ch0001.md", "# 计划\n")):
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(text, encoding="utf-8")
    draft = ws / "chapters/drafts/ch0001.md"
    draft.write_text("# 借炉\n\n他瞳孔骤然紧缩，倒抽一口凉气。\n\n---\n\n她嘴角扯出一抹弧度。\n\n字数：3200\n", encoding="utf-8")
    lint = json.loads(nv("lint", "1").stdout)
    joined = " ".join(lint["issues"])
    check(all(k in joined for k in ("瞳孔一缩", "倒吸一口凉气", "嘴角勾起", "分割线")), "lint：神态套语变体与分割线报 issue")
    check(any("写作报告" in w for w in lint["warnings"]), "lint：章末混入字数统计报 warning")
    draft.write_text("# 借炉\n\n" + "炉火很旺。" * 30 + "\n", encoding="utf-8")
    lint = json.loads(nv("lint", "1").stdout)
    check(any("目标上限 60" in w for w in lint["warnings"]), "lint：大纲 target_words 覆盖全局字数区间")
    draft.write_text("# 借炉\n\n炉火很旺，他把铁钳递过去。\n", encoding="utf-8")
    ctx = nv("context", "1", "--for", "editor").stdout
    check("本轮是第 1 轮评审" in ctx, "editor 上下文包写明评审轮次")
    r = route()
    check(r["action"] == "checker+editor" and r["round"] == 1, "首轮评审路由带 round=1")
    reviews = ws / "chapters/reviews"
    polish = {"chapter": 1, "round": 1, "verdict": "polish", "issues": [{"severity": "error"}]}
    (reviews / "ch0001.json").write_text(json.dumps(polish), encoding="utf-8")
    (reviews / "ch0001.check.json").write_text('{"chapter": 1, "findings": []}', encoding="utf-8")
    check(route()["action"] == "next-round", "第 1 轮 polish 先归档本轮评审")
    r = nv("next-round", "1")
    check(r.returncode == 0 and all((reviews / f"ch0001.r1{x}").exists() for x in (".json", ".check.json", ".draft.md")),
          "next-round 归档 review、check 与被评审的稿子")
    r = route()
    check(r["action"] == "writer:revise" and r["review"].endswith("ch0001.r1.json"), "草稿未改时路由到 writer:revise 并指向归档评审")
    draft.write_text("# 借炉\n\n炉火很旺，他接过铁钳。\n", encoding="utf-8")
    r = route()
    check(r["action"] == "checker+editor" and r["round"] == 2, "写手改完后进入第 2 轮评审")
    (reviews / "ch0001.json").write_text(json.dumps(polish), encoding="utf-8")   # editor 照旧写错 round=1
    (reviews / "ch0001.check.json").write_text('{"chapter": 1, "findings": []}', encoding="utf-8")
    check(route()["action"] == "finalize", "第 2 轮仍 polish 直接 finalize，不受 editor 自报 round 影响")
    check(nv("next-round", "1").returncode != 0, "第 2 轮后 next-round 被拒绝")
    (reviews / "ch0001.check.json").write_text('{"chapter": 1, "findings": [{"severity": "critical"}]}', encoding="utf-8")
    (reviews / "ch0001.json").write_text(json.dumps({**polish, "issues": []}), encoding="utf-8")
    check(route()["action"] == "blocked", "checker 的 critical 不经 editor 合并也计入 verdict")
    (reviews / "ch0001.check.json").write_text('{"chapter": 1, "findings": []}', encoding="utf-8")
    (reviews / "ch0001.json").write_text(json.dumps({**polish, "verdict": "rewrite", "issues": [{"severity": "critical"}]}), encoding="utf-8")
    check(route()["action"] == "blocked", "第 2 轮仍 rewrite 时 blocked")


def smoke_ledger(ws: Path) -> None:
    def nv(*args):
        return run(sys.executable, "tools/novel.py", *args, cwd=ws)

    chapters = [{"title": f"第{i}章", "characters": ["林越"]} for i in (1, 2, 3)]
    for rel, text in (("bible/premise.md", "# 故事前提\n"), ("bible/world/rules.md", "# 规则\n"), ("bible/world/calendar.md", "# 日历\n"),
                      ("outline/compass.json", "{}"), ("threads/registry.json", '[{"id":"T01","title":"炉底的字","type":"main","status":"planned"}]'),
                      ("bible/characters.json", '[{"name":"林越","slug":"lin-yue","tier":"core"}]'),
                      ("outline/volumes.json", json.dumps([{"title": "卷", "arcs": [{"title": "弧", "chapters": chapters}]}], ensure_ascii=False))):
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(text, encoding="utf-8")
    import re
    import urllib.request
    e = {k: v for k, v in os.environ.items() if k != "NOVEL_ROOT"}
    proc = subprocess.Popen([sys.executable, "tools/novel.py", "serve", "--port", "0"], cwd=ws, env=e,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:" + re.search(r"127\.0\.0\.1:(\d+)/", proc.stdout.readline()).group(1)

    def studio_t01():
        with urllib.request.urlopen(base + "/api/overview", timeout=10) as r:
            return next(t["status"] for t in json.loads(r.read())["threads"] if t["id"] == "T01")
    try:
        check(studio_t01() == "planned", "预览台起服务时 T01 尚未落地")
        _ledger_flow(ws, nv)
        check(studio_t01() == "active", "别的进程 commit 后预览台无需重启就看到新账本")
    finally:
        proc.terminate()


def _ledger_flow(ws: Path, nv) -> None:
    locs = {1: "青石镇·铁匠铺", 2: "青石镇·客栈", 3: "黑水渡"}
    for n in (1, 2, 3):
        (ws / f"chapters/final/ch{n:04d}.md").write_text(f"# 第{n}章\n\n林越和老周在{locs[n]}说话。\n", encoding="utf-8")
        facts = {"chapter": n, "title": f"第{n}章", "summary": "…", "key_events": ["…"], "time": {"day_start": n, "day_end": n},
                 "scenes": [{"id": f"ch{n:04d}-s1", "day": n, "location": locs[n], "characters": ["林越", "老周"], "summary": f"林越在{locs[n]}"}],
                 "threads": [{"id": "T01", "action": "plant" if n == 1 else "advance", "note": f"ch{n}"}]
                            + ([{"action": "plant", "title": "老周的旧伤", "type": "foreshadow", "promise": "…", "note": "…"}] if n == 2 else []),
                 "knowledge": [{"who": "林越", "fact": f"第{n}章的秘密", "status": "knows"}],
                 "locations_end": {"林越": locs[n]}, "cast_intros": [{"name": "老周", "brief_role": "铁匠"}] if n == 1 else []}
        (ws / f"chapters/facts/ch{n:04d}.json").write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")
        r = nv("commit", str(n))
        check(r.returncode == 0, f"提交第 {n} 章 ({r.stderr.strip()[:80] or 'ok'})")
    def ledger_counts():
        tl = (ws / "ledger/timeline.jsonl").read_text(encoding="utf-8").strip().splitlines()
        cast = json.loads((ws / "ledger/cast.json").read_text())
        th = json.loads((ws / "ledger/threads.json").read_text())
        return len(tl), cast["老周"]["count"], len(th[0]["milestones"]), len(th)
    before = ledger_counts()
    check(before == (3, 3, 3, 2), f"三章提交后账本计数正确 {before}")
    check(json.loads((ws / "threads/registry.json").read_text())[0].get("milestones") is None, "commit 不再改写 architect 的 registry")
    r = nv("commit", "2", "--force")
    check(r.returncode == 0 and ledger_counts() == before, f"commit --force 重提 plant 过新线程的旧章：不误报、不重复追加 ({r.stdout.strip()[:120]})")
    ctx = nv("context", "2", "--for", "writer").stdout
    check("第1章的秘密" in ctx and "第3章的秘密" not in ctx and "黑水渡" not in ctx, "返工第 2 章时上下文只含第 1 章为止的知识与位置")
    rec = json.loads(nv("recall", "--entity", "林越", "--before", "2").stdout)
    check(rec["state"]["location"] == "青石镇·铁匠铺" and len(rec["knowledge"]) == 1, "recall --before 的状态投影也截止在前一章")
    # 0.4 及以前：commit 把运行字段写进了 registry
    reg = json.loads((ws / "threads/registry.json").read_text())
    reg[0].update(status="active", planted_at=1, last_touched=3, milestones=[{"chapter": 1}, {"chapter": 2}, {"chapter": 3}])
    (ws / "threads/registry.json").write_text(json.dumps(reg), encoding="utf-8")
    r = nv("rebuild")
    check(r.returncode == 0 and ledger_counts() == before, "旧 registry 带运行字段时 rebuild 不重复 milestones")


def smoke_studio(ws: Path) -> None:
    import re
    import urllib.error
    import urllib.request

    e = {k: v for k, v in os.environ.items() if k != "NOVEL_ROOT"}
    proc = subprocess.Popen([sys.executable, "tools/novel.py", "serve", "--port", "0"], cwd=ws, env=e,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        m = re.search(r"http://127\.0\.0\.1:(\d+)/", proc.stdout.readline())
        check(m is not None, "serve 打印本机地址")
        base = f"http://127.0.0.1:{m.group(1)}"

        def call(method, path, body=None, headers=None):
            h = {"X-Novel-Studio": "1", **(headers or {})} if method != "GET" else dict(headers or {})
            req = urllib.request.Request(base + path, method=method, headers=h,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as err:
                return err.code, err.read().decode()

        code, html = call("GET", "/")
        check(code == 200 and "小说预览台" in html, "GET / 返回预览台页面")
        code, body = call("GET", "/api/overview")
        check(code == 200 and json.loads(body)["status"]["route"]["action"] == "architect:foundation", "overview 带 status 与 route")
        code, _ = call("GET", "/api/overview", headers={"Host": "evil.example"})
        check(code == 403, "非本机 Host 被拒绝（防 DNS rebinding）")
        code, _ = call("GET", "/api/file?path=tools/novel.py")
        check(code == 403, "tools/ 不可读")
        code, _ = call("PUT", "/api/file", {"path": "ledger/cast.json", "text": "{}"})
        check(code == 403, "ledger/ 不可写")
        code, _ = call("PUT", "/api/file", {"path": "bible/world/rules.md", "text": "x"}, headers={"X-Novel-Studio": ""})
        check(code == 403, "缺自定义请求头的写请求被拒绝")
        code, _ = call("PUT", "/api/file", {"path": "outline/compass.json", "text": "{bad"})
        check(code == 422, "JSON 文件格式错误时拒绝保存")

        draft = "chapters/drafts/ch0001.md"
        _, body = call("GET", f"/api/file?path={draft}")
        cur = json.loads(body)
        (ws / draft).write_text(cur["text"] + "外部改动\n", encoding="utf-8")
        code, _ = call("PUT", "/api/file", {"path": draft, "text": "覆盖", "sha": cur["sha"]})
        check(code == 409, "文件被别人改过后用旧 sha 保存返回 409")
        _, body = call("GET", f"/api/file?path={draft}")
        code, body = call("PUT", "/api/file", {"path": draft, "text": "# 第一章\n\n某种程度上他走了。\n", "sha": json.loads(body)["sha"]})
        check(code == 200 and json.loads(body)["lint"]["issues"], "保存草稿后返回 lint 结果")

        code, body = call("POST", "/api/comments", {"path": draft, "quote": "他走了", "text": "这里太突然"})
        cid = json.loads(body)["id"]
        check(code == 200 and json.loads(body)["chapter"] == 1, "批注按路径归到章节")
        r = run(sys.executable, "tools/novel.py", "context", "1", "--for", "writer", cwd=ws)
        check("这里太突然" in r.stdout and cid in r.stdout, "未处理批注进入 writer 上下文包")
        r = run(sys.executable, "tools/novel.py", "context", "1", "--for", "ledger", cwd=ws)
        check("这里太突然" not in r.stdout, "ledger 上下文包不带批注")
        code, _ = call("POST", "/api/comments/steer", {"id": cid})
        prog = json.loads((ws / "state/progress.json").read_text())
        check(code == 200 and prog["steer_queue"][-1].get("comment") == cid, "批注交给 Agent 后进入 steer 队列并带 comment id")
        r = run(sys.executable, "tools/novel.py", "comment", "resolve", cid, "已改", cwd=ws)
        r2 = run(sys.executable, "tools/novel.py", "context", "1", "--for", "writer", cwd=ws)
        check(r.returncode == 0 and "这里太突然" not in r2.stdout, "comment resolve 后不再注入上下文")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
