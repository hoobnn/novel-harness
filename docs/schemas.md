# 数据契约（所有 Agent 与工具共享的唯一口径）

所有文件 UTF-8。章节号四位补零：`ch0001`。故事内时间统一用「第几天」整数 `day`（第 1 天的定义写在 `bible/world/calendar.md`）。

## 目录

```
bible/                     静态设定（权威，改动需人工确认）
  premise.md               故事前提（14 节，见下）
  characters.json          角色机器索引（name/slug/aliases/tier/role）
  characters/<slug>.md     人物卡：人物卡 / 弧线计划 / 声音卡 / 秘密与知识边界
  world/rules.md           世界规则（category/rule/boundary）
  world/factions.md        势力（可选）
  world/geography.md       地理与行程耗时（可选，但有多地点必须写行程天数）
  world/calendar.md        日历：第 1 天定义、季节、节庆、关键日期
  style/voice.md           文风标准（写手与编辑共用）
  style/anti-ai-tone.md    去 AI 味判据（语义层）
  style/rules.json         机械规则：字数区间、禁用套句、疲劳词阈值、线程 stale 阈值
  style/user-rules.md      用户随手写的偏好（优先级最高，自然语言）
  style/samples.md         目标文风样张（可选，只借鉴手法不抄句子）
outline/
  compass.json             指南针：终局方向 / 活跃长线 / 规模估计
  volumes.json             分层大纲：卷 → 弧 → 章
threads/registry.json      故事线注册表
ledger/                    动态事实（只由 novel.py commit 写入）
  timeline.jsonl / knowledge.jsonl / state_changes.jsonl
  relationships.json / cast.json / characters/<slug>.json（状态投影）
chapters/
  plans/chNNNN.md          章节计划（节拍表 + 契约 + 线程预算）
  drafts/chNNNN.md         草稿（写手/修订者写入）
  reviews/chNNNN.json      编辑评审（含 round）
  reviews/chNNNN.check.json 连续性检查结论（checker 产出，与 review 同 round）
  final/chNNNN.md          定稿（finalize 后）
  facts/chNNNN.json        章节事实（账本员抽取，commit 时校验）
summaries/chapters|arcs|volumes/
state/progress.json        唯一进度事实源；state/decisions.jsonl 决策审计
state/checkpoints.jsonl    步级进度（哪章哪步何时完成），崩溃后据此续跑；只记事实不参与路由
index/novel.sqlite         全文索引（bigram 分词，可随时 reindex 重建，不入 git）
```

## bible/premise.md

`# 故事前提` 之后 14 个二级标题，名称必须一字不差：题材和基调 / 题材定位 / 核心冲突 / 主角目标 / 终局方向 / 写作禁区 / 差异化卖点 / 差异化钩子 / 核心兑现承诺 / 故事引擎 / 关系与成长主线 / 升级路径 / 中期转向 / 终局命题。

## bible/characters.json

```json
[{"name":"林越","slug":"lin-yue","aliases":["小越","那个外乡人"],"tier":"core","role":"主角"}]
```

`tier`: core / important / secondary。core 角色每章都会注入状态投影；其他只在大纲提及或线程关联时注入。次要有名配角不写在这里，由 `cast_intros` 自动登记到 `ledger/cast.json`。

## bible/characters/<slug>.md

```markdown
# 林越
## 人物卡
外貌 / 出身 / 能力 / 资源 / 性格特质（3-5 条）/ 核心欲望（want）/ 真正需要（need）/ 自我谎言（lie）
## 弧线计划
前期… 中期… 后期…；每卷预期转折点；与哪些线程绑定
## 声音卡
句长、口头禅、避免的词、潜台词比例、对不同对象的语气差异、示例台词 3 句
## 秘密与知识边界
他知道什么 / 不知道什么 / 绝不能在第 N 章前知道什么
```

## outline/volumes.json

```json
[{"title":"离乡","theme":"立足","final":false,"arcs":[
  {"title":"青石镇","goal":"…","estimated_chapters":10,"chapters":[
    {"title":"借炉","core_event":"…","hook":"…","scenes":["…","…"],
     "threads":["T01"],"characters":["林越"],"day_hint":"D1-D2"}]},
  {"title":"骨架弧","goal":"…","estimated_chapters":12}]}]
```

卷序号、弧序号、全书章号由数组顺序推导，不要手写 index。骨架弧没有 `chapters`。收官卷带 `"final": true`。

## outline/compass.json

```json
{"ending_direction":"…","open_threads":["T01","T03"],"estimated_scale":"预计 4-6 卷","last_updated":0}
```

## threads/registry.json（故事线）

```json
[{"id":"T01","title":"炉底的字","type":"mystery","status":"planned",
  "characters":["林越"],"planted_at":null,"last_touched":null,
  "promise":"炉底刻字指向林越身世","payoff":null,"payoff_window":[5,12],
  "milestones":[{"chapter":1,"action":"plant","note":"…"}]}]
```

- `type`: main / subplot / mystery / relationship / foreshadow / character_arc / world
- `status`: planned（架构师预登记，尚未在正文出现）/ active / dormant / resolved / abandoned
- `payoff_window`: [最早兑现章, 最晚兑现章]，工具据此报「到期」与「超期」
- 架构师可以预登记线程；正文第一次落地时账本员用 `plant` + 同一个 id，工具原地激活

## chapters/plans/chNNNN.md（章节计划）

```markdown
# 第 N 章 计划：<标题>
## 目标与冲突
## 视点
## 场景节拍表
| # | 地点 | 时间(D/时段) | 在场 | 目的 | 转折 | 离场状态 |
## 线程预算
- T01 advance：…  - T03 touch：…
## 契约
- required_beats: …
- forbidden_moves: …
- continuity_checks: …
- knowledge_boundaries: 谁在本章不能知道什么
- emotion_target / payoff_points / hook_goal
```

## chapters/facts/chNNNN.json（章节事实，账本员产出）

```json
{"chapter":12,"title":"…","summary":"120-200 字","pov":"林越",
 "time":{"day_start":12,"day_end":13,"non_linear":null},
 "locations_end":{"林越":"青石镇·客栈","苏眠":"青石镇·客栈"},
 "scenes":[{"id":"ch0012-s1","day":12,"time_of_day":"夜","location":"青石镇·客栈",
            "characters":["林越","苏眠"],"summary":"一句话，含可检索的实体与物件"}],
 "key_events":["…"],
 "threads":[{"id":"T01","action":"advance","note":"…"},
            {"action":"plant","title":"…","type":"foreshadow","promise":"…","characters":["…"],"payoff_window":[20,30],"note":"…"}],
 "knowledge":[{"who":"苏眠","fact":"炉底刻着一行字","status":"knows","source":"林越告知"}],
 "state_changes":[{"entity":"林越","field":"injury","old":"","new":"左臂骨折","reason":"…"}],
 "relationships":[{"a":"林越","b":"苏眠","relation":"结伴同行，互不信任","delta":"trust+1"}],
 "cast_intros":[{"name":"老周","brief_role":"青石镇铁匠"}],
 "timeline_extra":[{"day":10,"event":"（本章提到的过去事件）","characters":["…"],"location":"…"}],
 "hook_type":"reveal","dominant_thread":"T01",
 "outline_feedback":{"deviation":"…","suggestion":"…"}}
```

- `knowledge.status`: knows / suspects / believes_false / forgot
- `hook_type`: crisis / reveal / choice / interrupted_action / identity / clue / deadline / emotional_aftermath / relationship_shift / quiet
- `scenes[].characters` 只列有名角色；无名群众不列。新配角必须同时出现在 `cast_intros`。
- 校验命令：`python3 tools/novel.py validate-facts N`

## chapters/reviews/chNNNN.json（编辑评审）

```json
{"chapter":12,"round":1,"verdict":"accept|polish|rewrite",
 "scores":{"consistency":85,"character":80,"pacing":70,"continuity":90,"threads":75,"hook":80,"aesthetic":65},
 "contract_check":{"required_beats":"done|partial|failed","forbidden_moves":"clean|violated","knowledge_boundaries":"clean|violated"},
 "issues":[{"dimension":"aesthetic","severity":"critical|error|warning","description":"…",
            "evidence":"原文引用","suggestion":"具体改法","location":"段落定位"}],
 "revision_instructions":["按优先级排序的可执行修改指令"]}
```

verdict 规则：有 critical → rewrite；无 critical 有 error → polish；只有 warning → accept。

该规则由 `novel.py` 的 `effective_verdict()` 从 `issues` 反推校验：若声明的 verdict 比反推结果宽松，以反推结果为准（例如 issues 里有 critical 却写 accept，按 rewrite 处理）。

round 由主会话递增，最多 2 轮修订。第 2 轮后仍为 `polish` 则强制 finalize，把遗留问题写进 `outline_feedback`；仍为 `rewrite` 时 `route` 返回 `blocked`，主会话必须停下询问用户。

`chapters/reviews/chNNNN.check.json`（checker 产出）与 `chNNNN.json` 必须同时存在且 `round` 一致，否则 `route` 判定本轮未完成、重派 `checker+editor`。

## summaries

- `summaries/chapters/chNNNN.json` 由 commit 自动生成。
- `summaries/arcs/v1a2.json`: `{"volume":1,"arc":2,"title":"…","summary":"300-500 字","key_events":[],"character_snapshots":[{"name":"…","status":"…","motivation":"…","relations":"…"}],"style_rules":{"prose":[],"dialogue":[{"name":"…","rules":[]}],"taboos":[]},"open_questions":[]}`
- `summaries/volumes/v1.json`: `{"volume":1,"title":"…","summary":"500-800 字","key_events":[],"threads_resolved":[],"threads_carried":[]}`

## state/progress.json

```json
{"phase":"init|foundation|writing|complete","next_chapter":3,"last_committed":2,
 "gate":"auto|per-chapter|per-arc","pending_revisions":[],"arc_reviews_done":["v1a1"],
 "volume_reviews_done":[],"steer_queue":[]}
```

只由 `novel.py` 写入。

## state/checkpoints.jsonl（步级进度）

```json
{"at":"2026-09-18T15:20:45+08:00","chapter":12,"step":"writer","detail":"草稿 3600 字"}
```

`commit` / `finalize` 自动落盘；其余步骤由主会话在子智能体返回并通过校验后手动记一条：
`python3 tools/novel.py checkpoint add 12 writer "草稿 3600 字"`。

**它不参与路由判定** —— `route` 仍只看产物文件是否存在，因此手动删文件也能自愈。
checkpoint 的用途是会话中断后用 `status.recent_steps` 快速看出「上次做到哪一步」，避免重跑整章。
