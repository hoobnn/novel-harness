#!/usr/bin/env python3
"""novel.py — 长篇小说创作 harness 的确定性事实层工具。

只依赖 Python 标准库。所有「可以用代码判定」的事情都在这里做：
进度路由、上下文装配、全文检索、时间线校验、故事线台账、人物状态/知识账本、
文体统计、提交校验与落盘。需要判断力的事情（写什么、怎么写、好不好）留给 Agent。

用法: python3 tools/novel.py <command> [args]   （在小说工作区内任意目录运行）

本文件随 harness 分发：`init` 会把它连同钩子与数据契约复制进新工作区，
工作区从此自洽，不依赖插件安装路径；`upgrade` 从插件目录刷新这些文件。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

__version__ = "0.2.0"
WORKSPACE_MARKER = "state/progress.json"      # 有它才算小说工作区
HARNESS_ROOT = Path(__file__).resolve().parent.parent   # 本文件所在的 harness（插件目录或工作区）
VENDORED = [                                   # 随 harness 版本走、init 复制进工作区、upgrade 刷新
    "tools/novel.py",
    "tools/hooks/post_write.sh",
    "docs/schemas.md",
    "docs/protocol.md",
]
TEMPLATE_DIR = "templates/workspace"           # 只在 init 时播种、之后归用户所有的文件
ROOTLESS_CMDS = {"", "-h", "--help", "version"}


def find_workspace(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / WORKSPACE_MARKER).exists():
            return d
    return None


def _resolve_root() -> Path:
    if "NOVEL_ROOT" in os.environ:
        return Path(os.environ["NOVEL_ROOT"]).resolve()
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    if cmd == "init":
        positional = [x for x in argv[1:] if not x.startswith("-")]
        return (Path(positional[0]) if positional else Path.cwd()).resolve()
    ws = find_workspace(Path.cwd())
    if ws:
        return ws
    if cmd in ROOTLESS_CMDS:
        return Path.cwd()
    sys.exit(f"当前目录不是小说工作区（向上没有找到 {WORKSPACE_MARKER}）。"
             f"先在目标目录运行 `python3 {sys.argv[0]} init`，或用 NOVEL_ROOT 指定工作区。")


ROOT = _resolve_root()

P = {
    "progress": ROOT / "state/progress.json",
    "decisions": ROOT / "state/decisions.jsonl",
    "checkpoints": ROOT / "state/checkpoints.jsonl",
    "premise": ROOT / "bible/premise.md",
    "characters": ROOT / "bible/characters.json",
    "char_dir": ROOT / "bible/characters",
    "world_dir": ROOT / "bible/world",
    "calendar": ROOT / "bible/world/calendar.md",
    "style_rules": ROOT / "bible/style/rules.json",
    "voice": ROOT / "bible/style/voice.md",
    "volumes": ROOT / "outline/volumes.json",
    "compass": ROOT / "outline/compass.json",
    "threads": ROOT / "threads/registry.json",
    "timeline": ROOT / "ledger/timeline.jsonl",
    "knowledge": ROOT / "ledger/knowledge.jsonl",
    "state_changes": ROOT / "ledger/state_changes.jsonl",
    "relationships": ROOT / "ledger/relationships.json",
    "cast": ROOT / "ledger/cast.json",
    "char_state_dir": ROOT / "ledger/characters",
    "plans": ROOT / "chapters/plans",
    "drafts": ROOT / "chapters/drafts",
    "final": ROOT / "chapters/final",
    "facts": ROOT / "chapters/facts",
    "reviews": ROOT / "chapters/reviews",
    "sum_ch": ROOT / "summaries/chapters",
    "sum_arc": ROOT / "summaries/arcs",
    "sum_vol": ROOT / "summaries/volumes",
    "db": ROOT / "index/novel.sqlite",
    "user_rules": ROOT / "bible/style/user-rules.md",
}

DEFAULT_STYLE_RULES = {
    "word_count": [2500, 5000],
    "forbidden_phrases": ["某种程度上", "值得注意的是", "不知为何", "五味杂陈"],
    "fatigue_words": {
        "不禁": 1, "竟然": 1, "仿佛": 2, "此外": 1, "然而": 2,
        "一丝": 2, "一抹": 2, "一缕": 2, "宛如": 1, "不由得": 1,
        "像一": 3, "沉默了": 2, "没有说话": 2, "几息": 3, "一息": 3, "数息": 2,
    },
    "thread_stale_after": 6,
}

PATTERNS = [
    ("矫正句『不是…而是…』", re.compile(r"不是[^。！？\n]{1,24}?[，、]?(?:而)?是")),
    ("计时量词『X息/X瞬』", re.compile(r"[一两二三四五六七八九十几数半][息瞬]")),
    ("明喻『像一/仿佛/如同/宛如』", re.compile(r"像一|仿佛|如同|宛如")),
    ("沉默节拍『沉默了/没有说话/没有回头』", re.compile(r"沉默了|没有说话|没有回头")),
    ("神态模板『眼中闪过/嘴角勾起/咬了咬唇』", re.compile(r"眼[中底]闪过|目光一凝|瞳孔一缩|眼眶微红|嘴角[微轻一]?[勾扬翘]|咬了咬唇|不可置信")),
    ("躯体反应『心头一紧/身子一颤/倒吸凉气』", re.compile(r"心头一[紧沉颤]|身子一[颤震僵]|倒吸(?:了)?一口凉气")),
    ("思维标记『心想/意识到/感到/觉得』", re.compile(r"心想|意识到|感到|觉得")),
    ("抽象套话『一种说不出的/的意义在于』", re.compile(r"一种说不出的|说不清[的道]|的意义在于|真正的[^。！？\n]{1,10}是")),
]
SENT_SPLIT = re.compile(r"[。！？\n]+")
OPENING_TIME = re.compile(r"夜|清晨|黎明|天亮|醒来|晨光|一整夜")
HOOK_TYPES = ["crisis", "reveal", "choice", "interrupted_action", "identity", "clue", "deadline", "emotional_aftermath", "relationship_shift", "quiet"]
THREAD_TYPES = ["main", "subplot", "mystery", "relationship", "foreshadow", "character_arc", "world"]
THREAD_STATUS = ["planned", "active", "dormant", "resolved", "abandoned"]
THREAD_ACTIONS = ["plant", "advance", "touch", "resolve", "abandon"]
KNOWLEDGE_STATUS = ["knows", "suspects", "believes_false", "forgot"]
TRUST_RANGE = (-5, 5)          # 关系亲疏刻度：-5 死敌 / 0 中立 / 5 生死之交
TRUST_JUMP_LIMIT = 3           # 单章跳变上限，超过要求正文给出足够事件支撑


# ---------------------------------------------------------------- io helpers
def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def ch_name(n: int) -> str:
    return f"ch{n:04d}"


def ch_path(kind: str, n: int, ext: str) -> Path:
    return P[kind] / f"{ch_name(n)}.{ext}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(name: str) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", name.strip()).strip("-").lower()
    return s or "unnamed"


def wc(text: str) -> int:
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    return len(re.sub(r"\s+", "", body))


def style_rules() -> dict:
    rules = dict(DEFAULT_STYLE_RULES)
    rules.update(read_json(P["style_rules"], {}))
    return rules


def fail(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- outline
def flatten_outline(volumes: list[dict]) -> list[dict]:
    """展开分层大纲为扁平章节表，同时写入 volume/arc 定位与弧内序号。"""
    out, ch = [], 1
    for vi, v in enumerate(volumes, 1):
        for ai, a in enumerate(v.get("arcs", []), 1):
            chapters = a.get("chapters") or []
            for ci, e in enumerate(chapters, 1):
                e = dict(e)
                e.update(chapter=ch, volume=vi, arc=ai, arc_index=ci, arc_total=len(chapters),
                         arc_title=a.get("title", ""), arc_goal=a.get("goal", ""),
                         volume_title=v.get("title", ""), volume_theme=v.get("theme", ""),
                         volume_final=bool(v.get("final")))
                out.append(e)
                ch += 1
    return out


def locate(n: int) -> dict | None:
    for e in flatten_outline(read_json(P["volumes"], [])):
        if e["chapter"] == n:
            return e
    return None


def next_skeleton(volumes: list[dict]) -> dict | None:
    """返回第一个尚未展开章节的弧（骨架弧），没有则 None。"""
    for vi, v in enumerate(volumes, 1):
        for ai, a in enumerate(v.get("arcs", []), 1):
            if not a.get("chapters"):
                return {"volume": vi, "arc": ai, "title": a.get("title"), "goal": a.get("goal"),
                        "estimated_chapters": a.get("estimated_chapters")}
    return None


# ---------------------------------------------------------------- entities
def load_characters() -> list[dict]:
    return read_json(P["characters"], [])


def entity_names() -> dict[str, str]:
    """别名 -> 正式名 的映射，含核心角色与已登记配角。"""
    m: dict[str, str] = {}
    for c in load_characters():
        m[c["name"]] = c["name"]
        for a in c.get("aliases", []) or []:
            m[a] = c["name"]
    for name in read_json(P["cast"], {}):
        m.setdefault(name, name)
    return m


def canon(name: str, names: dict[str, str]) -> str:
    return names.get(name, name)


def mentions(text: str, names: dict[str, str]) -> list[str]:
    found = {canon(k, names) for k in names if k and k in text}
    return sorted(found)


# ---------------------------------------------------------------- sqlite fts
INDEX_VERSION = 2  # bump 后 db() 自动重建索引表

CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def bigrams(text: str) -> str:
    """把中文切成相邻两字对供 FTS5 unicode61 索引；非中文按原词保留。

    trigram 分词要求 token >= 3 字符，中文 2 字人名（「老周」）完全检索不到。
    bigram 是 CJK 全文检索的通行做法（Lucene CJKAnalyzer 同构）。
    """
    out: list[str] = []
    for seg in re.split(r"([\u4e00-\u9fff\u3400-\u4dbf]+)", text):
        if not seg:
            continue
        if CJK.match(seg):
            out.extend(seg[i:i + 2] for i in range(len(seg) - 1)) if len(seg) > 1 else out.append(seg)
        else:
            out.extend(w for w in re.split(r"\W+", seg.lower()) if w)
    return " ".join(out)


def db() -> sqlite3.Connection:
    P["db"].parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(P["db"])
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    if ver and ver != INDEX_VERSION:  # 旧格式索引：丢弃重建（索引是纯缓存，可 reindex 复原）
        for t in ("chunks", "scenes"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        ver = 0
    # raw 保存原文用于 snippet 展示，text 保存 bigram 形式用于匹配
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(chapter UNINDEXED, idx UNINDEXED, raw UNINDEXED, text, tokenize='unicode61')")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS scenes USING fts5(scene_id UNINDEXED, chapter UNINDEXED, day UNINDEXED, location UNINDEXED, characters UNINDEXED, raw UNINDEXED, text, tokenize='unicode61')")
    if not ver:
        con.execute(f"PRAGMA user_version={INDEX_VERSION}")
    return con


def chunk_text(text: str, size: int = 400) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip() and not p.startswith("#")]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > size and buf:
            out.append(buf)
            buf = p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        out.append(buf)
    return out


def index_chapter(con: sqlite3.Connection, n: int, text: str, facts: dict) -> None:
    con.execute("DELETE FROM chunks WHERE chapter=?", (n,))
    con.execute("DELETE FROM scenes WHERE chapter=?", (n,))
    for i, c in enumerate(chunk_text(text)):
        con.execute("INSERT INTO chunks(chapter, idx, raw, text) VALUES (?,?,?,?)", (n, i, c, bigrams(c)))
    for s in facts.get("scenes", []):
        # 场景卡把地点/人物一并并入可匹配文本，检索「老周」「铁匠铺」都能命中
        blob = " ".join([s.get("summary", ""), s.get("location", ""), " ".join(s.get("characters", []))])
        con.execute("INSERT INTO scenes(scene_id, chapter, day, location, characters, raw, text) VALUES (?,?,?,?,?,?,?)",
                    (s.get("id", ""), n, s.get("day"), s.get("location", ""),
                     " ".join(s.get("characters", [])), s.get("summary", ""), bigrams(blob)))
    con.commit()


def excerpt(raw: str, q: str, width: int = 120) -> str:
    """在原文里定位查询词并就近截取，命中处用【】标出。"""
    for tok in sorted(re.split(r"\s+", q.strip()), key=len, reverse=True):
        if tok and tok in raw:
            i = raw.index(tok)
            lo = max(0, i - width // 2)
            hi = min(len(raw), i + len(tok) + width // 2)
            body = raw[lo:i] + "【" + tok + "】" + raw[i + len(tok):hi]
            return ("…" if lo else "") + body + ("…" if hi < len(raw) else "")
    return raw[:width] + ("…" if len(raw) > width else "")


def fts_query(q: str) -> str:
    """把查询转成 bigram 短语。单字查询无法用 bigram 表达，交由调用方走 LIKE 兜底。"""
    phrases = []
    for tok in re.split(r"\s+", q.strip()):
        if not tok:
            continue
        if len(CJK.sub("", tok)) == 0 and len(tok) < 2:
            return ""  # 单个汉字无法用 bigram 表达，交给 LIKE 兜底
        bg = bigrams(tok)
        if not bg:
            continue
        # 同一个词的相邻字对必须连续出现，用 NEAR 会误配，这里用短语匹配
        phrases.append('"' + bg.replace('"', '""') + '"')
    return " OR ".join(phrases)


def search(q: str, before: int | None, limit: int) -> dict:
    con = db()
    res = {"scenes": [], "chunks": []}
    match = fts_query(q)
    cond = " AND chapter < ?" if before else ""
    args_tail = (before,) if before else ()
    if match:
        rows = con.execute(f"SELECT scene_id, chapter, day, location, characters, raw, bm25(scenes) FROM scenes WHERE scenes MATCH ?{cond} ORDER BY bm25(scenes) LIMIT ?",
                           (match, *args_tail, limit)).fetchall()
        res["scenes"] = [dict(zip(["scene_id", "chapter", "day", "location", "characters", "summary", "score"], r)) for r in rows]
        rows = con.execute(f"SELECT chapter, idx, raw, bm25(chunks) FROM chunks WHERE chunks MATCH ?{cond} ORDER BY bm25(chunks) LIMIT ?",
                           (match, *args_tail, limit)).fetchall()
        # raw 是原文，snippet 由调用方按查询词就近截取（bigram 索引无法直接用 fts5 snippet）
        res["chunks"] = [{"chapter": c, "idx": i, "snippet": excerpt(raw, q), "score": sc} for c, i, raw, sc in rows]
    else:  # 单字或纯符号查询兜底
        like = f"%{q.strip()}%"
        rows = con.execute(f"SELECT scene_id, chapter, day, location, characters, raw FROM scenes WHERE (raw LIKE ? OR characters LIKE ? OR location LIKE ?){cond} ORDER BY chapter DESC LIMIT ?",
                           (like, like, like, *args_tail, limit)).fetchall()
        res["scenes"] = [dict(zip(["scene_id", "chapter", "day", "location", "characters", "summary"], r)) for r in rows]
        rows = con.execute(f"SELECT chapter, idx, raw FROM chunks WHERE raw LIKE ?{cond} ORDER BY chapter DESC LIMIT ?",
                           (like, *args_tail, limit)).fetchall()
        res["chunks"] = [{"chapter": c, "idx": i, "snippet": excerpt(raw, q)} for c, i, raw in rows]
    return res


# ---------------------------------------------------------------- checkpoints
def checkpoint(chapter: int, step: str, detail: str = "") -> None:
    """记一步已完成的工作。崩溃或中断后 `status` 能据此说明从哪一步继续。

    只记录事实（哪章哪步在什么时候完成），不参与路由判定 ——
    路由仍由产物文件的存在性决定，这样手动删文件也能自愈。
    """
    append_jsonl(P["checkpoints"], [{"at": now(), "chapter": chapter, "step": step, "detail": detail}])


def last_checkpoints(chapter: int | None = None, limit: int = 8) -> list[dict]:
    rows = read_jsonl(P["checkpoints"])
    if chapter is not None:
        rows = [r for r in rows if r.get("chapter") == chapter]
    return rows[-limit:]


# ---------------------------------------------------------------- progress / route
def default_progress() -> dict:
    return {"phase": "init", "next_chapter": 1, "last_committed": 0, "gate": "per-arc",
            "pending_revisions": [], "arc_reviews_done": [], "volume_reviews_done": [],
            "steer_queue": [], "harness_version": __version__, "updated_at": now()}


def load_progress() -> dict:
    return read_json(P["progress"], default_progress())


def save_progress(p: dict) -> None:
    p["updated_at"] = now()
    write_json(P["progress"], p)


def foundation_missing() -> list[str]:
    missing = []
    if not P["premise"].exists():
        missing.append("bible/premise.md")
    if not load_characters():
        missing.append("bible/characters.json")
    if not (P["world_dir"] / "rules.md").exists():
        missing.append("bible/world/rules.md")
    if not P["calendar"].exists():
        missing.append("bible/world/calendar.md")
    if not read_json(P["volumes"], []):
        missing.append("outline/volumes.json")
    if not P["compass"].exists():
        missing.append("outline/compass.json")
    if not read_json(P["threads"], []):
        missing.append("threads/registry.json")
    if not P["voice"].exists():
        missing.append("bible/style/voice.md")
    return missing


def effective_verdict(review: dict) -> str:
    """按 docs/schemas.md 的规则从 issues 反推 verdict，取与声明值中更严格的一个。

    editor 可能给出与 issues 不符的 verdict（有 critical 却写 accept），
    这是能用代码判定的事，不依赖角色自觉。
    """
    sev = {i.get("severity") for i in review.get("issues", [])}
    derived = "rewrite" if "critical" in sev else "polish" if "error" in sev else "accept"
    rank = {"accept": 0, "polish": 1, "rewrite": 2}
    declared = review.get("verdict", "accept")
    return derived if rank.get(derived, 0) > rank.get(declared, 0) else declared


def route(p: dict) -> dict:
    """确定性路由：读事实，给出下一步。不调用任何模型。"""
    missing = foundation_missing()
    if missing:
        return {"action": "architect:foundation", "reason": "基础设定缺失", "missing": missing}
    if p["phase"] == "complete":
        return {"action": "done", "reason": "全书已完结"}
    if p.get("steer_queue"):
        return {"action": "steer", "reason": "有待处理的用户干预", "steer": p["steer_queue"][0]}
    if p.get("pending_revisions"):
        n = p["pending_revisions"][0]["chapter"]
        return {"action": "revise", "chapter": n, "reason": p["pending_revisions"][0].get("reason", "评审要求返工")}
    n = p["next_chapter"]
    last = p["last_committed"]
    volumes = read_json(P["volumes"], [])
    if last:
        prev = locate(last)
        if prev and prev["arc_index"] == prev["arc_total"]:
            key = f"v{prev['volume']}a{prev['arc']}"
            if key not in p.get("arc_reviews_done", []):
                return {"action": "editor:arc-review", "volume": prev["volume"], "arc": prev["arc"],
                        "chapters": [last - prev["arc_total"] + 1, last], "reason": "弧结束，需弧级评审+弧摘要+角色快照"}
            vol = volumes[prev["volume"] - 1]
            if prev["arc"] == len(vol.get("arcs", [])):
                vkey = f"v{prev['volume']}"
                if vkey not in p.get("volume_reviews_done", []):
                    return {"action": "editor:volume-review", "volume": prev["volume"], "reason": "卷结束，需卷摘要"}
                if prev.get("volume_final"):
                    return {"action": "architect:finale-check", "reason": "收官卷已写完，确认完结"}
                if prev["volume"] == len(volumes):
                    return {"action": "architect:new-volume", "reason": "当前卷已写完且没有下一卷"}
    entry = locate(n)
    if entry is None:
        sk = next_skeleton(volumes)
        if sk:
            return {"action": "architect:expand-arc", "reason": "下一弧仍是骨架，需要展开章节", **sk}
        return {"action": "architect:new-volume", "reason": "大纲耗尽"}
    if not ch_path("plans", n, "md").exists():
        return {"action": "planner", "chapter": n, "reason": "无章节计划"}
    if not ch_path("drafts", n, "md").exists():
        return {"action": "writer", "chapter": n, "reason": "无草稿"}
    review = read_json(ch_path("reviews", n, "json"), None)
    check = read_json(P["reviews"] / f"{ch_name(n)}.check.json", None)
    if review is None or check is None:
        missing_side = []
        if check is None:
            missing_side.append("checker")
        if review is None:
            missing_side.append("editor")
        return {"action": "checker+editor", "chapter": n, "reason": "草稿待检查与评审",
                "missing": missing_side}
    if review.get("round", 0) != check.get("round", review.get("round", 0)):
        return {"action": "checker+editor", "chapter": n, "reason": "check 与 review 轮次不一致，需重跑本轮",
                "missing": ["checker", "editor"]}
    verdict = effective_verdict(review)
    rnd = review.get("round", 0)
    if verdict == "rewrite" and rnd >= 2:
        return {"action": "blocked", "chapter": n,
                "reason": "修订 2 轮后仍为 rewrite，按 CLAUDE.md 需停下询问用户"}
    if verdict in ("rewrite", "polish") and rnd < 2:
        return {"action": "writer:revise", "chapter": n, "reason": f"评审结论 {verdict}", "round": rnd + 1}
    if not ch_path("final", n, "md").exists():
        return {"action": "finalize", "chapter": n, "reason": "评审通过，草稿待定稿"}
    if not ch_path("facts", n, "json").exists():
        return {"action": "ledger", "chapter": n, "reason": "定稿待抽取事实"}
    return {"action": "commit", "chapter": n, "reason": "事实已抽取，待提交"}


# ---------------------------------------------------------------- threads
def load_threads() -> list[dict]:
    return read_json(P["threads"], [])


def thread_view(last_committed: int, stale_after: int) -> list[dict]:
    out = []
    for t in load_threads():
        t = dict(t)
        lt = t.get("last_touched") or t.get("planted_at") or 0
        t["idle"] = last_committed - lt if lt else None
        t["stale"] = bool(t["status"] in ("active", "dormant") and t["idle"] is not None and t["idle"] >= stale_after)
        pw = t.get("payoff_window")
        t["payoff_due"] = bool(pw and t["status"] not in ("resolved", "abandoned") and last_committed + 1 >= pw[0])
        t["payoff_overdue"] = bool(pw and t["status"] not in ("resolved", "abandoned") and last_committed >= pw[1])
        out.append(t)
    return out


# ---------------------------------------------------------------- character projection
def char_state_path(name: str) -> Path:
    return P["char_state_dir"] / f"{slugify(name)}.json"


def load_char_state(name: str) -> dict:
    return read_json(char_state_path(name), {"name": name, "location": None, "fields": {}, "knowledge": [],
                                             "relations": {}, "first_seen": None, "last_seen": None, "appearances": 0})


def character_card(name: str) -> str:
    for c in load_characters():
        if c["name"] == name:
            md = P["char_dir"] / f"{c.get('slug') or slugify(name)}.md"
            return read_text(md)
    return ""


# ---------------------------------------------------------------- facts validation
def validate_facts(n: int, facts: dict) -> list[str]:
    errs: list[str] = []
    names = entity_names()
    known = set(names.values())
    new_cast = {c["name"] for c in facts.get("cast_intros", []) if c.get("name")}
    for k in ("title", "summary", "key_events", "scenes", "threads", "time"):
        if k not in facts:
            errs.append(f"缺少字段 {k}")
    if facts.get("chapter") not in (None, n):
        errs.append(f"chapter 字段 {facts.get('chapter')} 与目标章 {n} 不一致")
    t = facts.get("time") or {}
    if not isinstance(t.get("day_start"), int) or not isinstance(t.get("day_end"), int):
        errs.append("time.day_start / time.day_end 必须是整数（故事内第几天）")
    elif t["day_end"] < t["day_start"]:
        errs.append("time.day_end 早于 day_start")
    prev = read_json(ch_path("facts", n - 1, "json"), None) if n > 1 else None
    if prev and isinstance(t.get("day_start"), int) and not facts.get("time", {}).get("non_linear"):
        pe = prev.get("time", {}).get("day_end")
        if isinstance(pe, int) and t["day_start"] < pe:
            errs.append(f"时间倒流：本章 day_start={t['day_start']} 早于上章 day_end={pe}；若是闪回请在 time.non_linear 说明")
    for i, s in enumerate(facts.get("scenes", [])):
        for k in ("id", "location", "characters", "summary"):
            if not s.get(k):
                errs.append(f"scenes[{i}] 缺少 {k}")
        if not str(s.get("id", "")).startswith(ch_name(n)):
            errs.append(f"scenes[{i}].id 应以 {ch_name(n)}- 开头")
        for c in s.get("characters", []):
            if c not in known and c not in new_cast:
                errs.append(f"scenes[{i}] 角色「{c}」不在 characters.json / cast 中；若是新配角请写入 cast_intros，若是无名群众请不要列出")
    tids = {t["id"] for t in load_threads()}
    for i, u in enumerate(facts.get("threads", [])):
        if u.get("action") not in THREAD_ACTIONS:
            errs.append(f"threads[{i}].action 非法: {u.get('action')}")
        if u.get("action") == "plant":
            planned = {t["id"]: t for t in load_threads() if t.get("status") == "planned"}
            if u.get("id") and u["id"] in tids and u["id"] not in planned:
                errs.append(f"threads[{i}] plant 的 id {u['id']} 已存在且不是 planned 状态，应改用 advance/touch")
            if u.get("id") in planned:
                continue  # 预登记线程首次落地：沿用 registry 中的 title/type/promise
            for k in ("title", "type", "promise"):
                if not u.get(k):
                    errs.append(f"threads[{i}] plant 需要 {k}")
            if u.get("type") not in THREAD_TYPES:
                errs.append(f"threads[{i}].type 非法: {u.get('type')}")
        elif u.get("id") not in tids:
            errs.append(f"threads[{i}].id {u.get('id')} 不存在于 registry")
    for i, k in enumerate(facts.get("knowledge", [])):
        if k.get("status") not in KNOWLEDGE_STATUS:
            errs.append(f"knowledge[{i}].status 非法")
        if k.get("who") not in known and k.get("who") not in new_cast:
            errs.append(f"knowledge[{i}].who 「{k.get('who')}」未知实体")
        if not k.get("fact"):
            errs.append(f"knowledge[{i}] 缺少 fact")
    for i, c in enumerate(facts.get("state_changes", [])):
        if not (c.get("entity") and c.get("field") and c.get("new")):
            errs.append(f"state_changes[{i}] 需要 entity/field/new")
    rel_ledger = read_json(P["relationships"], {})
    for i, r in enumerate(facts.get("relationships", [])):
        if not (r.get("a") and r.get("b") and r.get("relation")) or r.get("a") == r.get("b"):
            errs.append(f"relationships[{i}] 需要 a/b/relation 且 a≠b")
            continue
        tr = r.get("trust")
        if tr is None:
            continue
        if not isinstance(tr, int) or not (TRUST_RANGE[0] <= tr <= TRUST_RANGE[1]):
            errs.append(f"relationships[{i}].trust 必须是 {TRUST_RANGE[0]}..{TRUST_RANGE[1]} 的整数（-5 死敌 / 0 中立 / 5 生死之交）")
            continue
        prev = rel_ledger.get("|".join(sorted([r["a"], r["b"]])), {}).get("trust")
        if isinstance(prev, int) and abs(tr - prev) > TRUST_JUMP_LIMIT:
            errs.append(f"relationships[{i}]「{r['a']}－{r['b']}」信任度从 {prev} 跳到 {tr}（跨度 {abs(tr - prev)}，上限 {TRUST_JUMP_LIMIT}）；"
                        f"关系突变需要足够事件支撑，若正文确有重大事件请拆成多章推进或在 outline_feedback 说明")
    for who, loc in (facts.get("locations_end") or {}).items():
        if who not in known and who not in new_cast:
            errs.append(f"locations_end 中「{who}」未知实体")
    if facts.get("hook_type") and facts["hook_type"] not in HOOK_TYPES:
        errs.append(f"hook_type 非法: {facts['hook_type']}，可选 {HOOK_TYPES}")
    if facts.get("dominant_thread") and facts["dominant_thread"] not in tids | {u.get("id") for u in facts.get("threads", []) if u.get("action") == "plant"}:
        errs.append("dominant_thread 不是已知线程")
    errs += check_quota(n, facts)
    return errs


def check_quota(n: int, facts: dict) -> list[str]:
    """进度配额：大纲给本章设的硬边界，防止只写氛围不推进剧情。

    `must_advance` 列出本章必须实质推进（advance/resolve，非 touch）的线程；
    `min_key_events` 是本章至少要发生的关键事件数。两者都是可选字段，
    architect 展开弧时按需要写，不写就不检查。
    """
    entry = locate(n)
    if not entry:
        return []
    errs: list[str] = []
    real = {u.get("id") for u in facts.get("threads", [])
            if u.get("action") in ("advance", "resolve", "plant") and u.get("id")}
    for tid in entry.get("must_advance") or []:
        if tid not in real:
            errs.append(f"进度配额：大纲要求本章实质推进线程 {tid}（advance/resolve），"
                        f"但 facts.threads 里没有它的 advance/resolve；"
                        f"若剧情确实改了走向，请在 outline_feedback 说明并让 architect 改大纲")
    lo = entry.get("min_key_events")
    if isinstance(lo, int) and len(facts.get("key_events") or []) < lo:
        errs.append(f"进度配额：大纲要求本章至少 {lo} 个关键事件，实际 {len(facts.get('key_events') or [])} 个")
    return errs


# ---------------------------------------------------------------- lint / stylestat
DIALOG = re.compile(r"[「『\u201c][^「『\u201c\u300d\u300f\u201d]*[\u300d\u300f\u201d]")


def split_dialog(body: str) -> tuple[str, str]:
    """拆出（叙述层, 对白层）。

    疲劳词与禁用套句只应约束叙述腔：人物口癖属于声音卡的一部分，
    在对白里出现「然而」「某种程度上」是刻画，不是 AI 腔。
    """
    dialog = " ".join(DIALOG.findall(body))
    narration = DIALOG.sub(" ", body)
    return narration, dialog


def lint_text(text: str, n: int | None = None) -> dict:
    rules = style_rules()
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    issues, warnings = [], []
    count = wc(text)
    lo, hi = rules.get("word_count", [0, 10**9])
    if count < lo * 0.8:
        warnings.append(f"字数 {count} 明显低于目标下限 {lo}")
    elif count > hi * 1.25:
        warnings.append(f"字数 {count} 明显高于目标上限 {hi}")
    narration, dialog = split_dialog(body)
    for ph in rules.get("forbidden_phrases", []):
        c = narration.count(ph)
        if c:
            issues.append(f"叙述中禁用套句「{ph}」出现 {c} 次")
        d = dialog.count(ph)
        if d:
            warnings.append(f"对白中出现禁用套句「{ph}」{d} 次；若非刻意的人物口癖请改掉")
    for w, limit in rules.get("fatigue_words", {}).items():
        c = narration.count(w)
        if c > limit:
            issues.append(f"叙述中疲劳词「{w}」出现 {c} 次（阈值 {limit}）")
        d = dialog.count(w)
        if d > limit * 2:  # 对白阈值放宽一倍，只有明显滥用才报
            warnings.append(f"对白中疲劳词「{w}」出现 {d} 次，偏多")
    if re.search(r"^\s*#{2,}\s", body, flags=re.M) or re.search(r"^\s*[一二三四五六七八九十]+[、.．]\s", body, flags=re.M):
        issues.append("正文中出现小标题/编号分段，应只保留章标题")
    if "——" in body and body.count("——") > 6:
        warnings.append(f"破折号出现 {body.count('——')} 次，偏多")
    patterns = {}
    for name, rx in PATTERNS:
        c = len(rx.findall(narration))
        if c:
            patterns[name] = c
    for name, c in patterns.items():
        if c >= 6:
            warnings.append(f"句式模式 {name} 本章 {c} 次")
    sents = [s.strip() for s in SENT_SPLIT.split(body) if len(s.strip()) >= 14]
    if n:
        prior = Counter()
        for m in range(max(1, n - 30), n):
            pt = read_text(ch_path("final", m, "md"))
            for s in set(x.strip() for x in SENT_SPLIT.split(pt) if len(x.strip()) >= 14):
                prior[s] += 1
        dup = [s for s in set(sents) if s in prior]
        if dup:
            issues.append(f"与前文逐字重复的长句 {len(dup)} 条，例如「{dup[0][:40]}」")
    lines = [l.strip() for l in body.strip().split("\n") if l.strip()]
    ending = lines[-1] if lines else ""
    opening = " ".join(lines[:2])
    dlg_chars = len(re.sub(r"\s+", "", dialog))
    dialog_ratio = round(dlg_chars / count, 2) if count else 0.0
    return {"chapter": n, "word_count": count, "issues": issues, "warnings": warnings, "patterns": patterns,
            "dialog_ratio": dialog_ratio,
            "ending_len": len(ending), "opening_time_word": bool(OPENING_TIME.search(opening[:30]))}


def stylestat(upto: int | None = None) -> dict:
    names = entity_names()
    chapters = []
    for f in sorted(P["final"].glob("ch*.md")):
        n = int(f.stem[2:])
        if upto and n > upto:
            continue
        chapters.append((n, read_text(f)))
    if len(chapters) < 3:
        return {"chapters": len(chapters), "note": "少于 3 章不出统计"}
    allt = "\n".join(t for _, t in chapters)
    n = len(chapters)
    pats = []
    for name, rx in PATTERNS:
        c = len(rx.findall(allt))
        if c:
            pats.append({"name": name, "total": c, "per_chapter": round(c / n, 1)})
    pats.sort(key=lambda x: -x["total"])
    sent_ch: dict[str, set] = defaultdict(set)
    for cn, t in chapters:
        for s in set(x.strip() for x in SENT_SPLIT.split(t) if len(x.strip()) >= 14):
            sent_ch[s].add(cn)
    repeated = sorted(({"text": s[:60], "chapters": sorted(c)} for s, c in sent_ch.items() if len(c) >= 2),
                      key=lambda x: -len(x["chapters"]))[:15]
    recent = [t for _, t in chapters[-20:]]
    grams: Counter = Counter()
    stop = set(names)
    for t in recent:
        body = re.sub(r"[^一-鿿]", " ", t)
        for seg in body.split():
            for k in (4, 5):
                for i in range(len(seg) - k + 1):
                    g = seg[i:i + k]
                    if not any(sw and sw in g for sw in stop):
                        grams[g] += 1
    top_phrases = [{"text": g, "count": c} for g, c in grams.most_common(60) if c >= max(4, n // 2)][:20]
    short = 0
    endings = []
    opening_time = 0
    for _, t in chapters:
        lines = [l.strip() for l in re.sub(r"^#.*$", "", t, flags=re.M).strip().split("\n") if l.strip()]
        if not lines:
            continue
        endings.append(len(lines[-1]))
        if len(lines[-1]) <= 30:
            short += 1
        if OPENING_TIME.search(" ".join(lines[:2])[:30]):
            opening_time += 1
    endings.sort()
    hooks = Counter()
    strands = Counter()
    for cn, _ in chapters:
        f = read_json(ch_path("facts", cn, "json"), {})
        if f.get("hook_type"):
            hooks[f["hook_type"]] += 1
        if f.get("dominant_thread"):
            strands[f["dominant_thread"]] += 1
    dratios = []
    for cn, t in chapters:
        b = re.sub(r"^#.*$", "", t, flags=re.M)
        _, dg = split_dialog(b)
        w = wc(t)
        if w:
            dratios.append((cn, round(len(re.sub(r"\s+", "", dg)) / w, 2)))
    dvals = sorted(v for _, v in dratios)
    return {"chapters": n, "avg_words": round(sum(wc(t) for _, t in chapters) / n),
            "dialog_ratio": {"median": dvals[len(dvals) // 2] if dvals else 0,
                             "lowest": sorted(dratios, key=lambda x: x[1])[:5]},
            "patterns": pats, "top_phrases": top_phrases, "repeated_sentences": repeated,
            "ending": {"short_ratio": round(short / n, 2), "median_len": endings[len(endings) // 2] if endings else 0},
            "opening_time_rate": round(opening_time / n, 2),
            "hook_types_recent": dict(Counter({k: v for k, v in hooks.items()}).most_common()),
            "dominant_threads": dict(strands.most_common())}


# ---------------------------------------------------------------- deterministic continuity check
def check_chapter(n: int, facts: dict | None) -> dict:
    """事实层连续性检查。facts 可为 None（只检查文本层面）。"""
    text = read_text(ch_path("drafts", n, "md")) or read_text(ch_path("final", n, "md"))
    names = entity_names()
    findings: list[dict] = []
    p = load_progress()
    rules = style_rules()
    present = mentions(text, names)
    # 位置连续性：上章末位置 vs 本章首个场景位置
    if facts:
        first_scene = (facts.get("scenes") or [{}])[0]
        for who in first_scene.get("characters", []):
            st = load_char_state(who)
            if st.get("location") and first_scene.get("location") and st["location"] != first_scene["location"]:
                findings.append({"kind": "location", "severity": "warning",
                                 "msg": f"「{who}」上章末在「{st['location']}」，本章开场在「{first_scene['location']}」，正文需有位移交代或本章 time 上留出行程"})
        # 已死亡/离场角色再出场
        for who in present:
            st = load_char_state(who)
            status = (st.get("fields") or {}).get("status", "")
            if status and any(k in status for k in ("死亡", "已死", "身亡")):
                findings.append({"kind": "status", "severity": "critical", "msg": f"「{who}」状态为「{status}」，本章正文仍提及，请确认是回忆/尸体/误判"})
        # 知识越界：本章 knowledge 里 knows 的事实与账本 believes_false 冲突等交给 LLM；这里只提示可用账本
    # 关系突变：trust 跳变虽在 validate-facts 拦截，这里给 checker 一个更早的提示
    if facts:
        rel_l = read_json(P["relationships"], {})
        for r in facts.get("relationships", []):
            tr = r.get("trust")
            prev = rel_l.get("|".join(sorted([r.get("a", ""), r.get("b", "")])), {}).get("trust")
            if isinstance(tr, int) and isinstance(prev, int) and abs(tr - prev) >= 2:
                findings.append({"kind": "relationship", "severity": "warning",
                                 "msg": f"「{r['a']}－{r['b']}」信任度 {prev} → {tr}，请确认正文有足够事件支撑这个变化"})
    # 线程：本章计划涉及的线程与 facts 中推进的线程
    plan = read_text(ch_path("plans", n, "md"))
    planned = set(re.findall(r"\bT\d{2,3}\b", plan))
    touched = {u.get("id") for u in (facts or {}).get("threads", []) if u.get("id")} if facts else set()
    if facts and planned - touched:
        findings.append({"kind": "thread", "severity": "warning", "msg": f"计划中提到但事实未记录推进的线程: {sorted(planned - touched)}"})
    stale = [t for t in thread_view(p["last_committed"], rules.get("thread_stale_after", 6)) if t["stale"]]
    overdue = [t for t in thread_view(p["last_committed"], rules.get("thread_stale_after", 6)) if t["payoff_overdue"]]
    for t in stale:
        findings.append({"kind": "thread", "severity": "info", "msg": f"线程 {t['id']}「{t['title']}」已 {t['idle']} 章未推进"})
    for t in overdue:
        findings.append({"kind": "thread", "severity": "warning", "msg": f"线程 {t['id']}「{t['title']}」已超过兑现窗口 {t['payoff_window']}"})
    lint = lint_text(text, n)
    for i in lint["issues"]:
        findings.append({"kind": "style", "severity": "error", "msg": i})
    for w in lint["warnings"]:
        findings.append({"kind": "style", "severity": "warning", "msg": w})
    return {"chapter": n, "present": present, "findings": findings, "lint": lint}


# ---------------------------------------------------------------- context pack
def tail(text: str, chars: int = 900) -> str:
    body = text.strip()
    return body[-chars:] if len(body) > chars else body


def md_list(items, fmt=lambda x: str(x)) -> str:
    return "\n".join(f"- {fmt(x)}" for x in items) if items else "- （无）"


# 每个角色实际用得上的上下文段落。装配时按需注入，避免把整包喂给所有角色：
# ledger 只做结构化抽取，不需要文风与评审教训；checker 只核事实，不需要声音卡与口头禅镜像。
ROLE_NEEDS = {
    "planner": {"outline", "compass", "summaries", "timeline", "threads_full", "characters",
                "knowledge", "cast", "retrieval", "lessons", "style_brief"},
    "writer":  {"outline", "compass", "summaries", "prev_tail", "timeline", "threads_full",
                "characters", "knowledge", "voice_card", "cast", "retrieval", "lessons",
                "style_full", "style_mirror", "plan"},
    "checker": {"outline", "summaries", "timeline", "threads_full", "characters", "knowledge",
                "cast", "retrieval", "plan", "deterministic"},
    "editor":  {"outline", "compass", "summaries", "prev_tail", "threads_full", "characters",
                "voice_card", "lessons", "style_full", "style_mirror", "plan", "deterministic"},
    "ledger":  {"outline", "summaries", "timeline", "threads_brief", "characters", "knowledge",
                "cast", "retrieval"},
}


def needs(role: str, section: str) -> bool:
    return section in ROLE_NEEDS.get(role, set())


def build_context(n: int, role: str) -> str:
    p = load_progress()
    rules = style_rules()
    names = entity_names()
    entry = locate(n)
    out: list[str] = [f"# 第 {n} 章 上下文包（role={role}，生成于 {now()}）", ""]
    out.append(f"进度：已提交 {p['last_committed']} 章；gate={p['gate']}；phase={p['phase']}")
    if entry:
        out += ["", "## 位置与大纲",
                f"卷 {entry['volume']}《{entry['volume_title']}》主题：{entry['volume_theme']}",
                f"弧 {entry['arc']}《{entry['arc_title']}》第 {entry['arc_index']}/{entry['arc_total']} 章。弧目标：{entry['arc_goal']}",
                f"本章大纲标题：{entry.get('title', '')}",
                f"核心事件：{entry.get('core_event', '')}",
                f"章末钩子（规划）：{entry.get('hook', '')}",
                "场景：", md_list(entry.get("scenes", [])),
                f"涉及线程：{entry.get('threads', [])}",
                f"预期出场：{entry.get('characters', [])}"]
        quota = []
        if entry.get("must_advance"):
            quota.append(f"必须实质推进（advance/resolve，touch 不算）：{entry['must_advance']}")
        if entry.get("min_key_events"):
            quota.append(f"关键事件至少 {entry['min_key_events']} 个")
        if quota:
            out += ["", "## 本章进度配额（硬边界，commit 时校验）"] + [f"- {q}" for q in quota]
        nxt = locate(n + 1)
        if nxt:
            out += [f"下一章预告：《{nxt.get('title', '')}》— {nxt.get('core_event', '')}"]
        if entry.get("volume_final"):
            out.append("**注意：本卷为收官卷，禁止新开长线。**")
    else:
        out += ["", "## 位置与大纲", "（本章尚无大纲条目）"]
    # compass
    compass = read_json(P["compass"], {})
    if compass and needs(role, "compass"):
        out += ["", "## 指南针", f"终局方向：{compass.get('ending_direction', '')}",
                f"活跃长线：{compass.get('open_threads', [])}", f"规模估计：{compass.get('estimated_scale', '')}"]
    # summaries: layered
    out += ["", "## 前情（分层摘要）"]
    vols = sorted(P["sum_vol"].glob("v*.json"))
    cur_vol = entry["volume"] if entry else 10**9
    for f in vols:
        v = read_json(f, {})
        vn = v.get("volume") or 0
        if vn == cur_vol:
            continue
        if vn >= cur_vol - 1:  # 相邻一卷给全文
            out.append(f"- 卷 {vn}《{v.get('title', '')}》：{v.get('summary', '')}")
        else:  # 更早的卷只留标题，细节靠指南针与检索
            out.append(f"- 卷 {vn}《{v.get('title', '')}》（更早，需细节用 `novel.py search`）")
    for f in sorted(P["sum_arc"].glob("v*.json")):
        a = read_json(f, {})
        if entry and (a.get("volume"), a.get("arc")) == (entry["volume"], entry["arc"]):
            continue
        if entry and a.get("volume") != entry["volume"]:
            continue
        out.append(f"- 弧 v{a.get('volume')}a{a.get('arc')}《{a.get('title', '')}》：{a.get('summary', '')}")
    recent_n = 3 if p["last_committed"] > 50 else 5
    start = max(1, n - recent_n)
    for m in range(start, n):
        s = read_json(ch_path("sum_ch", m, "json"), None)
        if s:
            out.append(f"- 第 {m} 章《{s.get('title', '')}》[D{s.get('day_start')}–D{s.get('day_end')}]：{s.get('summary', '')}")
    if n > 1 and needs(role, "prev_tail"):
        prev_text = read_text(ch_path("final", n - 1, "md"))
        if prev_text:
            out += ["", "## 上一章结尾（衔接语气与节奏，不要复述）", "```", tail(prev_text), "```"]
    # timeline
    tl = read_jsonl(P["timeline"]) if needs(role, "timeline") else []
    if tl:
        out += ["", "## 时间线（最近事件）", f"日历规则见 bible/world/calendar.md。上章结束于故事第 {tl[-1].get('day')} 天。"]
        out.append(md_list(tl[-8:], lambda e: f"ch{e['chapter']} D{e.get('day')} {e.get('time_of_day', '')} @{e.get('location', '')}: {e['event']} [{','.join(e.get('characters', []))}]"))
    # threads
    tv = thread_view(p["last_committed"], rules.get("thread_stale_after", 6))
    active = [t for t in tv if t["status"] in ("active", "dormant", "planned")]
    plan_ids = set(entry.get("threads") or []) if entry else set()
    # 分级：本章相关/到期/超期给全量，其余只给一行，避免后期几十条线程压垮上下文
    # 三级：本章涉及/到期 -> 全量；仅停滞 -> 一行提醒；其余 -> 只留 id 与标题
    hot = [t for t in active if t["id"] in plan_ids or t["payoff_due"] or t["payoff_overdue"]]
    warm = [t for t in active if t not in hot and t["stale"]]
    cold = [t for t in active if t not in hot and t not in warm]
    if active and needs(role, "threads_full"):
        out += ["", "## 故事线台账（本章必须至少推进一条主线或到期线）"]
        for t in hot:
            flags = []
            if t["stale"]:
                flags.append(f"⚠ {t['idle']} 章未动")
            if t["payoff_overdue"]:
                flags.append("⚠ 超过兑现窗口")
            elif t["payoff_due"]:
                flags.append("兑现窗口已到")
            if t["id"] in plan_ids:
                flags.append("★本章计划涉及")
            last = (t.get("milestones") or [{}])[-1]
            last_s = f"上次 ch{t.get('last_touched')}：{last.get('note', '')}" if t.get("last_touched") else "尚未在正文落地"
            out.append(f"- {t['id']} [{t['type']}/{t['status']}] {t['title']}：承诺「{t.get('promise', '')}」；{last_s}；兑现窗口 {t.get('payoff_window')} {' '.join(flags)}")
        for t in warm:
            out.append(f"- {t['id']}《{t['title']}》已 {t['idle']} 章未推进 ⚠（细节用 `novel.py threads --id {t['id']}`）")
        if cold:
            out.append("其余在途线程（需要细节用 `novel.py threads --id T0X`）："
                       + "、".join(f"{t['id']}《{t['title']}》" for t in cold))
    elif active and needs(role, "threads_brief"):
        out += ["", "## 在途故事线（仅供登记动作时对号入座）"]
        out.append("、".join(f"{t['id']}《{t['title']}》[{t['status']}]" for t in active))
    # characters
    chars_in = set(entry.get("characters", []) if entry else [])
    for t in active:
        if entry and t["id"] in (entry.get("threads") or []):
            chars_in.update(t.get("characters", []))
    core = [c for c in load_characters() if c.get("tier", "core") in ("core",)]
    chars_in.update(c["name"] for c in core)
    out += ["", "## 人物（当前状态投影 + 知识账本）", "完整人物卡：bible/characters/<slug>.md；需要更多时用 `novel.py character <名字>`。"]
    for c in load_characters():
        if c["name"] not in chars_in:
            continue
        st = load_char_state(c["name"])
        know = [k for k in st.get("knowledge", [])][-8:]
        out.append(f"### {c['name']}（{c.get('role', '')}，别名 {c.get('aliases', [])}）")
        out.append(f"- 位置：{st.get('location')}；最后出场 ch{st.get('last_seen')}；状态字段：{json.dumps(st.get('fields', {}), ensure_ascii=False)}")
        if st.get("relations"):
            out.append(f"- 关系：{json.dumps(st['relations'], ensure_ascii=False)}")
        if know and needs(role, "knowledge"):
            out.append("- 知道/怀疑：" + "；".join(f"[{k['status']} ch{k['chapter']}] {k['fact']}" for k in know))
        if needs(role, "voice_card"):
            card = character_card(c["name"])
            voice = re.search(r"##\s*声音卡\s*\n([\s\S]*?)(?=\n## |\Z)", card)
            if voice:
                out.append("- 声音卡：\n" + "\n".join("  " + l for l in voice.group(1).strip().split("\n")))
    cast = read_json(P["cast"], {})
    recent_cast = sorted(cast.items(), key=lambda kv: -(kv[1].get("last_seen") or 0))[:12] if needs(role, "cast") else []
    if recent_cast:
        out += ["", "## 近期活跃配角（再次出场前先 `novel.py recall --entity 名字` 找回口吻）"]
        out.append(md_list(recent_cast, lambda kv: f"{kv[0]}：{kv[1].get('brief_role', '')}（首见 ch{kv[1].get('first_seen')}，末见 ch{kv[1].get('last_seen')}，{kv[1].get('count')} 次）"))
    # retrieval: related scenes
    if entry and p["last_committed"] > 0 and needs(role, "retrieval"):
        q_terms = set()
        for c in entry.get("characters", []):
            q_terms.add(c)
        for s in entry.get("scenes", []):
            q_terms.update(mentions(s, names))
        rel = []
        seen = set()
        for term in list(q_terms)[:6]:
            for s in search(term, before=n, limit=4)["scenes"]:
                if s["scene_id"] not in seen:
                    seen.add(s["scene_id"])
                    rel.append(s)
        rel.sort(key=lambda s: -s["chapter"])
        if rel:
            out += ["", "## 检索到的相关历史场景（按需 `novel.py search` 深挖或直接读 chapters/final）"]
            out.append(md_list(rel[:12], lambda s: f"ch{s['chapter']} {s['scene_id']} D{s.get('day')} @{s.get('location')} [{s.get('characters')}]: {s.get('summary')}"))
    # style
    if needs(role, "style_full"):
        out += ["", "## 文风约束", read_text(P["voice"]).strip() or "（bible/style/voice.md 未写）"]
    elif needs(role, "style_brief"):
        out += ["", "## 文风约束（要点）", f"目标字数 {rules.get('word_count')}；禁用套句见 bible/style/rules.json；完整标准见 bible/style/voice.md"]
    ur = read_text(P["user_rules"]).strip()
    if ur and (needs(role, "style_full") or needs(role, "style_brief")):
        out += ["", "### 用户偏好（优先级高于默认文风）", ur]
    st = stylestat(upto=n - 1) if needs(role, "style_mirror") else {}
    if st.get("patterns") or st.get("top_phrases"):
        out += ["", "### 你自己的口头禅镜像（全书统计，本章主动压低）"]
        out.append("句式模式章均：" + "；".join(f"{x['name']} {x['per_chapter']}" for x in st.get("patterns", [])[:6]))
        if st.get("top_phrases"):
            out.append("近期高频短语：" + "、".join(x["text"] for x in st["top_phrases"][:12]))
        out.append(f"章末短句收尾占比 {st.get('ending', {}).get('short_ratio')}；开篇时间词率 {st.get('opening_time_rate')}；近期钩子类型 {st.get('hook_types_recent')}")
    # reviews lessons
    lessons = []
    for m in range(max(1, n - 5), n) if needs(role, "lessons") else []:
        r = read_json(ch_path("reviews", m, "json"), None)
        if r:
            for iss in r.get("issues", [])[:3]:
                if iss.get("severity") in ("critical", "error"):
                    lessons.append(f"ch{m} [{iss.get('dimension')}] {iss.get('description')}")
    if lessons:
        out += ["", "## 近期评审教训（不要重犯）", md_list(lessons)]
    # role-specific
    if role == "planner":
        out += ["", "## 规划要求", f"目标字数区间：{rules.get('word_count')}；线程 stale 阈值：{rules.get('thread_stale_after')} 章。",
                "输出 chapters/plans/chNNNN.md，包含：目标、冲突、视点、场景节拍表（每场景：地点/时间/在场/目的/转折/离场状态）、线程预算（推进哪几条、各自动作）、契约（required_beats / forbidden_moves / continuity_checks / knowledge_boundaries / emotion_target / hook_goal）。"]
    if role == "writer":
        plan = read_text(ch_path("plans", n, "md"))
        out += ["", "## 本章计划（chapters/plans）", plan or "（缺失，先运行 planner）"]
    if role in ("checker", "editor"):
        plan = read_text(ch_path("plans", n, "md"))
        out += ["", "## 本章计划与契约", plan or "（无）"]
        out += ["", "## 确定性检查结果", "```json", json.dumps(check_chapter(n, read_json(ch_path("facts", n, "json"), None)), ensure_ascii=False, indent=1), "```"]
    return "\n".join(out)


# ---------------------------------------------------------------- commit
def commit(n: int, force: bool = False) -> None:
    final = read_text(ch_path("final", n, "md"))
    if not final:
        fail(f"chapters/final/{ch_name(n)}.md 不存在")
    facts = read_json(ch_path("facts", n, "json"), None)
    if facts is None:
        fail(f"chapters/facts/{ch_name(n)}.json 不存在")
    errs = validate_facts(n, facts)
    if errs:
        print("\n".join("- " + e for e in errs))
        fail("facts 校验失败", 2)
    p = load_progress()
    if n != p["next_chapter"] and not force:
        fail(f"当前 next_chapter={p['next_chapter']}，不能提交第 {n} 章（--force 覆盖）")
    digest = sha(final)
    if facts.get("committed_sha") == digest and not force:
        print(f"第 {n} 章已按相同正文提交过，跳过。")
        return
    names = entity_names()
    # cast
    cast = read_json(P["cast"], {})
    for c in facts.get("cast_intros", []):
        cast.setdefault(c["name"], {"brief_role": c.get("brief_role", ""), "first_seen": n, "last_seen": n, "count": 0})
    present = set(mentions(final, {**names, **{k: k for k in cast}}))
    for s in facts.get("scenes", []):
        present.update(s.get("characters", []))
    for name in present:
        if name in cast:
            cast[name]["last_seen"] = n
            cast[name]["count"] = cast[name].get("count", 0) + 1
    write_json(P["cast"], cast)
    # timeline
    t = facts["time"]
    tl_rows = []
    for s in facts.get("scenes", []):
        tl_rows.append({"chapter": n, "day": s.get("day", t["day_start"]), "time_of_day": s.get("time_of_day", ""),
                        "location": s.get("location", ""), "event": s.get("summary", ""), "characters": s.get("characters", []),
                        "scene_id": s.get("id")})
    for e in facts.get("timeline_extra", []):
        tl_rows.append({"chapter": n, **e})
    append_jsonl(P["timeline"], tl_rows)
    # knowledge / state changes
    append_jsonl(P["knowledge"], [{"chapter": n, **k} for k in facts.get("knowledge", [])])
    append_jsonl(P["state_changes"], [{"chapter": n, **c} for c in facts.get("state_changes", [])])
    # relationships
    rel = read_json(P["relationships"], {})
    for r in facts.get("relationships", []):
        key = "|".join(sorted([r["a"], r["b"]]))
        ent = rel.setdefault(key, {"a": r["a"], "b": r["b"], "relation": "", "trust": None, "history": []})
        ent["relation"] = r["relation"]
        ent["chapter"] = n
        if r.get("trust") is not None:
            ent["trust"] = r["trust"]
        ent["history"].append({"chapter": n, "relation": r["relation"],
                               "delta": r.get("delta", ""), "trust": r.get("trust")})
    write_json(P["relationships"], rel)
    # character projections
    for name in present:
        st = load_char_state(name)
        st["first_seen"] = st.get("first_seen") or n
        st["last_seen"] = n
        st["appearances"] = st.get("appearances", 0) + 1
        write_json(char_state_path(name), st)
    for who, loc in (facts.get("locations_end") or {}).items():
        st = load_char_state(who)
        st["location"] = loc
        write_json(char_state_path(who), st)
    for c in facts.get("state_changes", []):
        st = load_char_state(c["entity"])
        st.setdefault("fields", {})[c["field"]] = c["new"]
        write_json(char_state_path(c["entity"]), st)
    for k in facts.get("knowledge", []):
        st = load_char_state(k["who"])
        st.setdefault("knowledge", []).append({"chapter": n, "fact": k["fact"], "status": k["status"], "source": k.get("source", "")})
        write_json(char_state_path(k["who"]), st)
    for r in facts.get("relationships", []):
        for a, b in ((r["a"], r["b"]), (r["b"], r["a"])):
            st = load_char_state(a)
            st.setdefault("relations", {})[b] = (
                f"{r['relation']}（信任 {r['trust']:+d}）" if r.get("trust") is not None else r["relation"])
            write_json(char_state_path(a), st)
    # threads
    threads = load_threads()
    by_id = {x["id"]: x for x in threads}
    for u in facts.get("threads", []):
        if u["action"] == "plant" and u.get("id") in by_id and by_id[u["id"]].get("status") == "planned":
            th = by_id[u["id"]]
            th.update(status="active", planted_at=n, last_touched=n)
            th.setdefault("milestones", []).append({"chapter": n, "action": "plant", "note": u.get("note", "")})
        elif u["action"] == "plant":
            tid = u.get("id") or f"T{len(threads) + 1:02d}"
            while tid in by_id:
                tid = f"T{int(tid[1:]) + 1:02d}"
            th = {"id": tid, "title": u["title"], "type": u["type"], "status": "active",
                  "characters": u.get("characters", []), "planted_at": n, "last_touched": n,
                  "promise": u["promise"], "payoff": None, "payoff_window": u.get("payoff_window"),
                  "milestones": [{"chapter": n, "action": "plant", "note": u.get("note", "")}]}
            threads.append(th)
            by_id[tid] = th
            u["id"] = tid
        else:
            th = by_id[u["id"]]
            th["last_touched"] = n
            th.setdefault("milestones", []).append({"chapter": n, "action": u["action"], "note": u.get("note", "")})
            if u["action"] == "resolve":
                th["status"] = "resolved"
                th["payoff"] = u.get("note", "")
                th["resolved_at"] = n
            elif u["action"] == "abandon":
                th["status"] = "abandoned"
            elif th["status"] in ("planned", "dormant"):
                th["status"] = "active"
    write_json(P["threads"], threads)
    # summary
    write_json(ch_path("sum_ch", n, "json"), {"chapter": n, "title": facts["title"], "summary": facts["summary"],
                                             "key_events": facts.get("key_events", []), "characters": sorted(present),
                                             "pov": facts.get("pov"), "day_start": t["day_start"], "day_end": t["day_end"],
                                             "word_count": wc(final), "hook_type": facts.get("hook_type"),
                                             "dominant_thread": facts.get("dominant_thread")})
    # index
    index_chapter(db(), n, final, facts)
    # facts sha + progress
    facts["committed_sha"] = digest
    facts["committed_at"] = now()
    write_json(ch_path("facts", n, "json"), facts)
    p["last_committed"] = max(p["last_committed"], n)
    p["next_chapter"] = max(p["next_chapter"], n + 1)
    p["phase"] = "writing"
    p["pending_revisions"] = [r for r in p.get("pending_revisions", []) if r.get("chapter") != n]
    save_progress(p)
    append_jsonl(P["decisions"], [{"at": now(), "kind": "commit", "chapter": n, "sha": digest[:12], "words": wc(final)}])
    checkpoint(n, "commit", f"{wc(final)} 字，sha {digest[:12]}")
    entry = locate(n)
    flags = []
    if entry and entry["arc_index"] == entry["arc_total"]:
        flags.append("ARC_END")
        vol = read_json(P["volumes"], [])[entry["volume"] - 1]
        if entry["arc"] == len(vol.get("arcs", [])):
            flags.append("VOLUME_END")
    print(json.dumps({"committed": n, "words": wc(final), "next_chapter": p["next_chapter"], "flags": flags,
                      "route": route(p)}, ensure_ascii=False))


def reindex() -> None:
    if P["db"].exists():
        P["db"].unlink()
    con = db()
    k = 0
    for f in sorted(P["final"].glob("ch*.md")):
        n = int(f.stem[2:])
        index_chapter(con, n, read_text(f), read_json(ch_path("facts", n, "json"), {}))
        k += 1
    print(f"reindexed {k} chapters")


def sync_check() -> list[dict]:
    out = []
    for f in sorted(P["final"].glob("ch*.md")):
        n = int(f.stem[2:])
        facts = read_json(ch_path("facts", n, "json"), None)
        if not facts or not facts.get("committed_sha"):
            continue
        if sha(read_text(f)) != facts["committed_sha"]:
            out.append({"chapter": n, "reason": "正文已被手动修改，事实需重新抽取（删除 facts 的 committed_sha 后重跑 ledger + commit --force）"})
    return out


# ---------------------------------------------------------------- init / upgrade / status
def _copy_file(src: Path, dst: Path) -> None:
    import shutil
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _vendor(src_root: Path, overwrite: bool) -> list[str]:
    """把随版本走的工具与契约复制进工作区。返回实际写入的相对路径。"""
    done = []
    for rel in VENDORED:
        src, dst = src_root / rel, ROOT / rel
        if not src.exists():
            continue
        if overwrite or not dst.exists():
            _copy_file(src, dst)
            done.append(rel)
    return done


def _seed_templates(src_root: Path) -> list[str]:
    """播种模板：已存在的文件一律不动；CLAUDE.md 若已存在则只追加带标记的段落。"""
    done = []
    tpl = src_root / TEMPLATE_DIR
    if not tpl.is_dir():
        return done
    for f in sorted(tpl.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(tpl)
        dst = ROOT / rel
        if rel.name == "CLAUDE.md":
            block = f.read_text(encoding="utf-8")
            marker = "<!-- novel-harness:begin -->"
            if not dst.exists():
                dst.write_text(block, encoding="utf-8")
                done.append(str(rel))
            elif marker not in dst.read_text(encoding="utf-8"):
                with dst.open("a", encoding="utf-8") as out:
                    out.write("\n\n" + block)
                done.append(str(rel) + " (appended)")
            continue
        if not dst.exists():
            _copy_file(f, dst)
            done.append(str(rel))
    return done


def _link_or_copy(src_name: str, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    try:
        dst.symlink_to(src_name)
    except OSError:
        import shutil
        shutil.copy2(dst.parent / src_name, dst)


WORKSPACE_PERMISSIONS = ["Bash(python3 tools/novel.py:*)", "Bash(git add:*)", "Bash(git commit:*)",
                         "Bash(git status:*)", "Bash(git log:*)", "Bash(git diff:*)"]


def _write_claude_settings(standalone: bool) -> str | None:
    """工作区级 .claude/settings.json：只在不存在时写。
    插件模式只放权限白名单（钩子由插件提供，避免双触发）；standalone 模式连钩子一起写。"""
    dst = ROOT / ".claude/settings.json"
    if dst.exists():
        return None
    cfg: dict = {"permissions": {"allow": WORKSPACE_PERMISSIONS}}
    if standalone:
        cfg["hooks"] = {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [
            {"type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR\"/tools/hooks/post_write.sh"}]}]}
    write_json(dst, cfg)
    return ".claude/settings.json"


def _vendor_claude_components(src_root: Path) -> list[str]:
    """standalone：把角色与 skill 复制到工作区 .claude/，不装插件也能用。"""
    import shutil
    done = []
    for sub in ("agents", "skills"):
        src = src_root / sub
        if not src.is_dir():
            continue
        dst = ROOT / ".claude" / sub
        if dst.exists():
            continue
        shutil.copytree(src, dst)
        done.append(f".claude/{sub}/")
    return done


CODEX_SANDBOX = {"checker": "read-only", "judge": "read-only"}   # 其余角色要写工作区文件


def _parse_agent_md(path: Path) -> tuple[dict, str]:
    """读角色 markdown：frontmatter（name/description/...）与正文。"""
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = text[end + 4:].lstrip("\n")
    return meta, body


def _toml_str(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _vendor_codex_agents(src_root: Path, overwrite: bool = False) -> list[str]:
    """把 agents/*.md 转成 Codex 子智能体定义 .codex/agents/<role>.toml。
    Codex 按 name 字段识别；model 不写（模型名不通用，沿用会话默认）；只读角色给 read-only 沙箱。"""
    src = src_root / "agents"
    if not src.is_dir():
        return []
    dst_dir = ROOT / ".codex/agents"
    done = []
    for f in sorted(src.glob("*.md")):
        meta, body = _parse_agent_md(f)
        name = meta.get("name") or f.stem
        dst = dst_dir / f"{name}.toml"
        if dst.exists() and not overwrite:
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        body = body.replace('"""', "'''")   # 正文里不能出现 TOML 多行字符串的结束符
        tq = chr(34) * 3   # TOML 多行字符串定界符
        toml = (f"# 由 novel-harness 从 agents/{f.name} 生成；改角色请改源文件后 novel.py upgrade\n"
                f"name = {_toml_str(name)}\n"
                f"description = {_toml_str(meta.get('description', ''))}\n"
                f"sandbox_mode = {_toml_str(CODEX_SANDBOX.get(name, 'workspace-write'))}\n"
                "developer_instructions = " + tq + "\n" + body.rstrip() + "\n" + tq + "\n")
        dst.write_text(toml, encoding="utf-8")
        done.append(f".codex/agents/{name}.toml")
    return done


def init_project(standalone: bool = False) -> None:
    if ROOT.resolve() == HARNESS_ROOT.resolve() and (HARNESS_ROOT / TEMPLATE_DIR).is_dir():
        fail("这是 harness 本身的目录，不能当作小说工作区。到一个空目录（或你的小说目录）里运行 init。")
    for k in ("char_dir", "world_dir", "plans", "drafts", "final", "facts", "reviews", "sum_ch", "sum_arc", "sum_vol", "char_state_dir"):
        P[k].mkdir(parents=True, exist_ok=True)
    P["style_rules"].parent.mkdir(parents=True, exist_ok=True)
    fresh = not P["progress"].exists()
    if fresh:
        save_progress(default_progress())
    if not P["style_rules"].exists():
        write_json(P["style_rules"], DEFAULT_STYLE_RULES)
    if not P["threads"].exists():
        write_json(P["threads"], [])
    if not P["relationships"].exists():
        write_json(P["relationships"], {})
    if not P["cast"].exists():
        write_json(P["cast"], {})
    db().close()

    written = _seed_templates(HARNESS_ROOT)
    written += _vendor(HARNESS_ROOT, overwrite=False)
    if (ROOT / "CLAUDE.md").exists():
        _link_or_copy("CLAUDE.md", ROOT / "AGENTS.md")
    if standalone:
        written += _vendor_claude_components(HARNESS_ROOT)
        written += _vendor_codex_agents(HARNESS_ROOT)
    settings = _write_claude_settings(standalone)
    if settings:
        written.append(settings)
    if standalone and not settings:
        print("提示：.claude/settings.json 已存在，未写入钩子；standalone 模式请手动加入 tools/hooks/post_write.sh 的 PostToolUse 钩子。")

    print(f"initialized novel workspace at {ROOT} (novel-harness {__version__}, {'新建' if fresh else '已存在，幂等'})")
    for rel in written:
        print(f"  + {rel}")
    if not (ROOT / ".git").exists() and find_git_root(ROOT) is None:
        print("提示：工作区还不是 git 仓库；每章提交依赖 git，建议先 `git init`。")


def find_git_root(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def harness_cache() -> Path | None:
    """skill 单独安装（npx skills 等）时 init.sh 克隆的本地缓存；能刷新就顺手刷新。"""
    env = os.environ.get("NOVEL_HARNESS_SRC")
    cache = Path(env).resolve() if env else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "novel-harness/src"
    if not (cache / "tools/novel.py").exists():
        return None
    if not env and (cache / ".git").exists():
        import subprocess
        try:
            subprocess.run(["git", "-C", str(cache), "pull", "--ff-only", "-q"], timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return cache


def _refresh_standalone_components(src_root: Path) -> list[str]:
    """standalone 工作区：刷新复制进 .claude/ 的角色；skill 只在不是 npx skills 托管时刷新。"""
    import shutil
    done = []
    agents = ROOT / ".claude/agents"
    if agents.is_dir() and (src_root / "agents").is_dir():
        for f in (src_root / "agents").glob("*.md"):
            shutil.copy2(f, agents / f.name)
        done.append(".claude/agents/")
    skills = ROOT / ".claude/skills"
    if (skills / "novel-next/SKILL.md").exists() and not (ROOT / "skills-lock.json").exists() and (src_root / "skills").is_dir():
        for d in (src_root / "skills").iterdir():
            if d.is_dir():
                shutil.copytree(d, skills / d.name, dirs_exist_ok=True)
        done.append(".claude/skills/")
    if (ROOT / ".codex/agents").is_dir() or agents.is_dir():   # standalone 工作区：旧版本没生成过也补上
        done += _vendor_codex_agents(src_root, overwrite=True)
    return done


def upgrade_workspace(src: str | None) -> None:
    """从 harness（插件目录或本地缓存）刷新工作区里随版本走的文件。模板与用户文件不动。"""
    if src:
        src_root = Path(src).resolve()
    elif HARNESS_ROOT.resolve() != ROOT.resolve():
        src_root = HARNESS_ROOT
    elif os.environ.get("CLAUDE_PLUGIN_ROOT"):
        src_root = Path(os.environ["CLAUDE_PLUGIN_ROOT"]).resolve()
    elif harness_cache():
        src_root = harness_cache()  # type: ignore[assignment]
    else:
        fail("不知道从哪里升级：用插件目录下的 novel.py 运行（python3 <插件目录>/tools/novel.py upgrade），"
             "加 --from <harness 目录>，或设置 NOVEL_HARNESS_SRC")
    if not (src_root / "tools/novel.py").exists():
        fail(f"{src_root} 不是 novel-harness 目录（缺 tools/novel.py）")
    src_ver = re.search(r'^__version__ = "([^"]+)"', (src_root / "tools/novel.py").read_text(encoding="utf-8"), re.M)
    new_ver = src_ver.group(1) if src_ver else "unknown"
    p = load_progress()
    old_ver = p.get("harness_version", "unknown")
    done = _vendor(src_root, overwrite=True)
    done += _refresh_standalone_components(src_root)
    p["harness_version"] = new_ver
    save_progress(p)
    print(f"upgraded {ROOT}: {old_ver} -> {new_ver}")
    for rel in done:
        print(f"  ~ {rel}")


def status() -> dict:
    p = load_progress()
    r = route(p)
    rules = style_rules()
    tv = thread_view(p["last_committed"], rules.get("thread_stale_after", 6))
    return {"progress": p, "route": r, "foundation_missing": foundation_missing(),
            "harness": {"version": __version__, "root": str(ROOT)},
            "recent_steps": last_checkpoints(limit=5),
            "threads": {"active": sum(t["status"] == "active" for t in tv), "stale": [t["id"] for t in tv if t["stale"]],
                        "overdue": [t["id"] for t in tv if t["payoff_overdue"]]},
            "unsynced": sync_check(), "words_total": sum(wc(read_text(f)) for f in P["final"].glob("ch*.md"))}


# ---------------------------------------------------------------- recall
def recall(entity: str, before: int | None) -> dict:
    names = entity_names()
    name = canon(entity, names)
    lim = before or 10**9
    st = load_char_state(name)
    return {"name": name, "card": character_card(name)[:3000], "state": st,
            "timeline": [e for e in read_jsonl(P["timeline"]) if name in e.get("characters", []) and e["chapter"] < lim][-30:],
            "knowledge": [k for k in read_jsonl(P["knowledge"]) if k.get("who") == name and k["chapter"] < lim],
            "state_changes": [c for c in read_jsonl(P["state_changes"]) if c.get("entity") == name and c["chapter"] < lim],
            "relationships": {k: v for k, v in read_json(P["relationships"], {}).items() if name in (v.get("a"), v.get("b"))},
            "scenes": search(name, before, 20)["scenes"],
            "cast_entry": read_json(P["cast"], {}).get(name)}


# ---------------------------------------------------------------- cli
def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(prog="novel.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="在目录里建立小说工作区：目录骨架、状态、模板、随版本走的工具与契约（幂等）")
    s.add_argument("dir", nargs="?", help="目标目录，默认当前目录")
    s.add_argument("--standalone", action="store_true", help="不装插件也能用：把角色与 skill 复制到工作区 .claude/ 并写入钩子")
    s = sub.add_parser("upgrade", help="从插件目录刷新工作区里的 novel.py / 钩子 / 数据契约")
    s.add_argument("--from", dest="src", help="harness 目录；缺省用当前运行的 novel.py 所在 harness 或 $CLAUDE_PLUGIN_ROOT")
    sub.add_parser("version", help="打印 harness 版本")
    sub.add_parser("status", help="进度 + 确定性路由（下一步该做什么）")
    s = sub.add_parser("context", help="装配第 N 章的上下文包（Markdown）")
    s.add_argument("chapter", type=int)
    s.add_argument("--for", dest="role", default="writer", choices=["planner", "writer", "checker", "editor", "ledger"])
    s = sub.add_parser("search", help="全文/场景检索")
    s.add_argument("query")
    s.add_argument("--before", type=int)
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("recall", help="召回一个实体的全部账本信息")
    s.add_argument("--entity", required=True)
    s.add_argument("--before", type=int)
    s = sub.add_parser("timeline", help="时间线查询")
    s.add_argument("--from", dest="d0", type=int)
    s.add_argument("--to", dest="d1", type=int)
    s.add_argument("--entity")
    s.add_argument("--chapter", type=int)
    s = sub.add_parser("threads", help="故事线台账")
    s.add_argument("--stale", action="store_true")
    s.add_argument("--id")
    s = sub.add_parser("character", help="人物卡 + 状态投影")
    s.add_argument("name")
    s = sub.add_parser("locate", help="章节在卷/弧中的位置与大纲条目")
    s.add_argument("chapter", type=int)
    s = sub.add_parser("validate-facts", help="校验 chapters/facts/chNNNN.json")
    s.add_argument("chapter", type=int)
    s = sub.add_parser("check", help="确定性连续性检查（草稿或定稿）")
    s.add_argument("chapter", type=int)
    s = sub.add_parser("lint", help="文体机械检查")
    s.add_argument("target", help="章节号或文件路径")
    s = sub.add_parser("stylestat", help="全书文体统计")
    s.add_argument("--upto", type=int)
    s = sub.add_parser("commit", help="提交定稿：校验事实、更新账本、索引、进度")
    s.add_argument("chapter", type=int)
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("finalize", help="把草稿复制为定稿（评审通过后）")
    s.add_argument("chapter", type=int)
    s.add_argument("--force", action="store_true", help="允许覆盖已提交章节的定稿")
    s = sub.add_parser("review-done", help="登记弧/卷评审完成：v1a2 或 v1")
    s.add_argument("key")
    s = sub.add_parser("queue-revision", help="把已提交章节加入返工队列")
    s.add_argument("chapter", type=int)
    s.add_argument("--reason", default="")
    s = sub.add_parser("steer", help="登记/弹出用户干预：add <text> | pop")
    s.add_argument("op", choices=["add", "pop", "list"])
    s.add_argument("text", nargs="?")
    s = sub.add_parser("gate", help="设置人工闸门：auto | per-chapter | per-arc")
    s.add_argument("mode", choices=["auto", "per-chapter", "per-arc"])
    s = sub.add_parser("set-phase", help="设置 phase：foundation|writing|complete")
    s.add_argument("phase", choices=["init", "foundation", "writing", "complete"])
    s = sub.add_parser("checkpoint", help="记录/查看步级进度：add <章> <步骤> [说明] | list [章]")
    s.add_argument("op", choices=["add", "list"])
    s.add_argument("chapter", nargs="?", type=int)
    s.add_argument("step", nargs="?")
    s.add_argument("detail", nargs="?", default="")
    sub.add_parser("sync", help="检测被手动修改过的定稿")
    sub.add_parser("reindex", help="重建全文索引")
    a = ap.parse_args(argv)

    if a.cmd == "init":
        init_project(a.standalone)
    elif a.cmd == "upgrade":
        upgrade_workspace(a.src)
    elif a.cmd == "version":
        print(__version__)
    elif a.cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    elif a.cmd == "context":
        print(build_context(a.chapter, a.role))
    elif a.cmd == "search":
        print(json.dumps(search(a.query, a.before, a.limit), ensure_ascii=False, indent=1))
    elif a.cmd == "recall":
        print(json.dumps(recall(a.entity, a.before), ensure_ascii=False, indent=1))
    elif a.cmd == "timeline":
        rows = read_jsonl(P["timeline"])
        if a.d0 is not None:
            rows = [r for r in rows if (r.get("day") or 0) >= a.d0]
        if a.d1 is not None:
            rows = [r for r in rows if (r.get("day") or 0) <= a.d1]
        if a.entity:
            rows = [r for r in rows if a.entity in r.get("characters", [])]
        if a.chapter:
            rows = [r for r in rows if r["chapter"] == a.chapter]
        for r in rows:
            print(f"ch{r['chapter']:04d} D{r.get('day')} {r.get('time_of_day', ''):<4} @{r.get('location', '')}: {r['event']} [{','.join(r.get('characters', []))}]")
    elif a.cmd == "threads":
        p = load_progress()
        tv = thread_view(p["last_committed"], style_rules().get("thread_stale_after", 6))
        if a.id:
            tv = [t for t in tv if t["id"] == a.id]
        if a.stale:
            tv = [t for t in tv if t["stale"] or t["payoff_overdue"]]
        print(json.dumps(tv, ensure_ascii=False, indent=1))
    elif a.cmd == "character":
        print(json.dumps(recall(a.name, None), ensure_ascii=False, indent=1))
    elif a.cmd == "locate":
        print(json.dumps(locate(a.chapter), ensure_ascii=False, indent=1))
    elif a.cmd == "validate-facts":
        facts = read_json(ch_path("facts", a.chapter, "json"), None)
        if facts is None:
            fail("facts 文件不存在")
        errs = validate_facts(a.chapter, facts)
        print("\n".join("- " + e for e in errs) if errs else "OK")
        sys.exit(2 if errs else 0)
    elif a.cmd == "check":
        print(json.dumps(check_chapter(a.chapter, read_json(ch_path("facts", a.chapter, "json"), None)), ensure_ascii=False, indent=1))
    elif a.cmd == "lint":
        if a.target.isdigit():
            n = int(a.target)
            text = read_text(ch_path("drafts", n, "md")) or read_text(ch_path("final", n, "md"))
        else:
            n = None
            m = re.search(r"ch(\d{4})", a.target)
            if m:
                n = int(m.group(1))
            text = read_text(Path(a.target))
        print(json.dumps(lint_text(text, n), ensure_ascii=False, indent=1))
    elif a.cmd == "stylestat":
        print(json.dumps(stylestat(a.upto), ensure_ascii=False, indent=1))
    elif a.cmd == "commit":
        commit(a.chapter, a.force)
    elif a.cmd == "finalize":
        d = read_text(ch_path("drafts", a.chapter, "md"))
        if not d:
            fail("草稿不存在")
        facts = read_json(ch_path("facts", a.chapter, "json"), None)
        if facts and facts.get("committed_sha") and not a.force:
            fail(f"第 {a.chapter} 章已提交；覆盖定稿会让账本与正文脱节。"
                 f"确需返工请走 queue-revision，或显式 --force")
        ch_path("final", a.chapter, "md").write_text(d, encoding="utf-8")
        checkpoint(a.chapter, "finalize", f"{wc(d)} 字")
        print(f"finalized ch{a.chapter:04d} ({wc(d)} 字)")
    elif a.cmd == "review-done":
        p = load_progress()
        key = "arc_reviews_done" if "a" in a.key else "volume_reviews_done"
        if a.key not in p.setdefault(key, []):
            p[key].append(a.key)
        save_progress(p)
        print(json.dumps(route(p), ensure_ascii=False))
    elif a.cmd == "queue-revision":
        p = load_progress()
        p.setdefault("pending_revisions", []).append({"chapter": a.chapter, "reason": a.reason, "at": now()})
        save_progress(p)
        print("queued")
    elif a.cmd == "steer":
        p = load_progress()
        q = p.setdefault("steer_queue", [])
        if a.op == "add":
            q.append({"text": a.text or "", "at": now()})
            save_progress(p)
        elif a.op == "pop":
            item = q.pop(0) if q else None
            save_progress(p)
            print(json.dumps(item, ensure_ascii=False))
        else:
            print(json.dumps(q, ensure_ascii=False, indent=1))
    elif a.cmd == "gate":
        p = load_progress()
        p["gate"] = a.mode
        save_progress(p)
        print(f"gate={a.mode}")
    elif a.cmd == "set-phase":
        p = load_progress()
        p["phase"] = a.phase
        save_progress(p)
        print(f"phase={a.phase}")
    elif a.cmd == "checkpoint":
        if a.op == "add":
            if a.chapter is None or not a.step:
                fail("用法：checkpoint add <章号> <步骤名> [说明]")
            checkpoint(a.chapter, a.step, a.detail)
            print(f"checkpoint ch{a.chapter:04d} {a.step}")
        else:
            print(json.dumps(last_checkpoints(a.chapter, 20), ensure_ascii=False, indent=1))
    elif a.cmd == "sync":
        print(json.dumps(sync_check(), ensure_ascii=False, indent=1))
    elif a.cmd == "reindex":
        reindex()


if __name__ == "__main__":
    main(sys.argv[1:])
