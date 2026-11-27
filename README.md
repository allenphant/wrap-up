# wrap-up

一個給 Claude Code 與 Codex 共用的收尾技能：把散落在對話裡的偏好與狀態，固定寫進兩個工具都讀得到的檔案，並把過時的內容封存起來而不是刪掉。

A session wrap-up skill shared by Claude Code and Codex: it captures the preferences and state buried in a conversation into files both tools can read, and archives what has gone stale instead of deleting it.

[繁體中文](#繁體中文) · [English](#english)

---

## 繁體中文

### 這個技能解決什麼問題

對話結束時，有價值的東西通常有兩種：**你講過的偏好**（「以後測試都放 tests/」）和**專案現在的狀態**（做到哪、卡在哪、哪條路走不通）。前者散在對話裡，下一個 session 就忘了；後者只存在你腦中。

`wrap-up` 把這兩件事各自寫成一個檔案，並且解決一個常被忽略的問題：**Claude Code 與 Codex 各有自己的記憶檔（`CLAUDE.md`、`AGENTS.md`）**。兩邊各寫一份必然走樣，所以這個技能採用單一真相來源 + 指標檔：

```
AGENTS.md      ← 唯一真相來源，所有規則都在這
CLAUDE.md      ← 只有一行 "@AGENTS.md"，把 Claude 導向上面那份
```

Claude Code 讀 `CLAUDE.md`，看到 `@AGENTS.md` 就展開匯入；Codex 直接讀 `AGENTS.md`。兩邊拿到同一份規則，專案在兩個工具間切換不需要任何手動動作。

> 這是實測結論，不是推論。實測於 Claude Code 2.1.278：只有 `AGENTS.md` 時讀得到；但只要另有一份沒有匯入它的 `CLAUDE.md`，`AGENTS.md` 就會被忽略。放一行 `@AGENTS.md` 的指標檔可避免這個情況（2.1.252 上只有 `AGENTS.md` 時讀不到，指標檔同樣解決）。Codex 側實測於 codex-cli 0.152.1。子目錄的巢狀記憶檔同樣適用。

### 執行流程：兩個階段

```
你輸入 /wrap-up
       │
       ▼
┌─ 階段一（不問你，直接做）────────────────────┐
│  1. 新偏好 append 進 AGENTS.md               │
│  2. 檢查／修復 CLAUDE.md 指標檔              │
│  3. 舊的 CURRENT_STATE.md 存進 states/       │
│  4. 寫入新的 CURRENT_STATE.md                │
│  5. 列出「建議封存」清單 —— 只列，不動        │
└──────────────────────────────────────────────┘
       │
       ├─ 沒有任何發現 ──────────────► 直接給第一句話（結束）
       │
       ▼  同一輪跳出核准選單，你勾選
┌─ 階段二（選單回答之後）──────────────────────┐
│  6. 只套用你核准的項目                        │
│  7. 回讀驗證                                  │
│  8. 給下一個 session 的第一句話               │
└──────────────────────────────────────────────┘
```

**為什麼寫入不等你核准**：wrap-up 的存在意義就是「在 session 死掉之前把脈絡存下來」。如果所有輸出都卡在你回覆之後，跑完 `/wrap-up` 就關掉終端的人會什麼都沒存到。所以**純新增的動作立刻執行，只有刪除與搬移需要核准**。

### 封存：解決 AGENTS.md 無限膨脹

`AGENTS.md` 會被載入**每一個** session，每一行過時規則都在永久收取 token。但直接刪掉又會弄丟脈絡。

封存同時解決兩邊：內容移到 `docs/wrap-up/`，**永遠不會被載入**，但留在磁碟上、可以 grep、可以復原。什麼都沒有被刪除，只是移出了 context window。

```
專案根/
├── AGENTS.md                     ← 每個 session 載入，保持精簡
├── CLAUDE.md                     ← 一行指標
├── CURRENT_STATE.md              ← 最新狀態
└── docs/wrap-up/
    ├── ARCHIVE.md                ← 封存的規則原文 + 所有搬移紀錄
    ├── states/
    │   ├── 2026-09-02-1134.md    ← 歷次狀態快照（自動，不需核准）
    │   └── 2026-09-04-0912.md
    └── files/
        └── docs/old-design.md    ← 封存的檔案，保留原始相對路徑
```

**兩類封存對象**

| 對象 | 判定依據 | 需要核准 |
|---|---|---|
| `AGENTS.md` 裡的規則 | 重複／矛盾／過時 | ✅ 要 |
| 專案裡的文件與資料檔 | 對話中講過已作廢，或 repo 內零引用且檔名帶 `old`／日期／`deprecated` 等 | ✅ 要 |
| 上一版 `CURRENT_STATE.md` | 每次覆寫前自動保存 | ❌ 不用（這是保存，不是刪除） |

**核准要拿得到判斷依據。** 提案清單裡每個檔案都會附上**實際跑過 `grep -rl` 的引用次數**，你才知道搬走會不會弄壞 import 或 build。技能不准用猜的。

**唯一的硬限制**：`AGENTS.md`、`CLAUDE.md`、`CURRENT_STATE.md` 自己不能被封存，`docs/wrap-up/` 底下的東西也不能。那會讓整套機制當場失效。

**檔案搬移保留原始相對路徑**（`docs/old-design.md` → `docs/wrap-up/files/docs/old-design.md`），是 git repo 就用 `git mv` 保留歷史，並在 `ARCHIVE.md` 記一筆 `原路徑 → 封存路徑`。要復原時路徑是明確的。

### 每次執行會對檔案結構做什麼

**情境 A — 全新專案**

```
執行前                        執行後
my-project/                   my-project/
└── src/                      ├── AGENTS.md          ← 新建：寫入本次對話出現的偏好
                              ├── CLAUDE.md          ← 新建：內容只有一行 @AGENTS.md
                              ├── CURRENT_STATE.md   ← 新建：狀態快照
                              └── src/
```

**情境 B — 既有專案，只有 CLAUDE.md（最常見的遷移）**

```
執行前                        執行後
my-project/                   my-project/
├── CLAUDE.md  (200 行規則)   ├── AGENTS.md          ← 200 行規則原封搬來，並附加本次新偏好
└── src/                      ├── CLAUDE.md          ← 內容變成一行 @AGENTS.md
                              ├── CURRENT_STATE.md   ← 新建
                              └── src/
```

**情境 C — CLAUDE.md 被別的工具汙染**（`/init` 覆寫、或另一個 agent 追加了規則）

```
執行前                        執行後
my-project/                   my-project/
├── AGENTS.md  (規則)         ├── AGENTS.md          ← 原內容 + CLAUDE.md 多出來的部分（一字不漏）
├── CLAUDE.md  (@AGENTS.md    ├── CLAUDE.md          ← 還原成一行 @AGENTS.md
│              + 3 條新規則)  ├── CURRENT_STATE.md
└── src/                      └── src/
```

**情境 D — 危險結構：CLAUDE.md 是 symlink**

```
執行前                        執行後
my-project/                   my-project/
├── AGENTS.md  (規則)         ├── AGENTS.md          ← 完全沒被動到
├── CLAUDE.md -> AGENTS.md    ├── CLAUDE.md          ← symlink 被 rm，改成真實檔案
└── src/                      ├── CURRENT_STATE.md
                              └── src/
```

> **為什麼 symlink 一定要換掉**：寫入 symlink 等於寫入目標檔。如果技能直接把「一行指標」寫進那個連結，整份 `AGENTS.md` 會被覆蓋成 `@AGENTS.md` 一行，並變成自我遞迴的 import —— 規則全數消失。技能因此在動任何檔案之前先檢查 symlink，先 `rm` 連結本身（不影響目標檔）再寫真實檔案。

**情境 E — 穩定狀態，且你核准了一項封存**

```
執行前                          執行後
my-project/                     my-project/
├── AGENTS.md  (含 3 條重複)    ├── AGENTS.md              ← 移除核准的那條（原文已進 ARCHIVE.md）
├── CLAUDE.md  (@AGENTS.md)     ├── CLAUDE.md              ← 不變
├── CURRENT_STATE.md            ├── CURRENT_STATE.md       ← 覆寫，沒進展的段落保留上一版
├── docs/                       ├── docs/
│   └── old-design.md           │   └── wrap-up/
└── src/                        │       ├── ARCHIVE.md     ← 規則原文 + 搬移紀錄
                                │       ├── states/2026-09-04-0912.md
                                │       └── files/docs/old-design.md
                                └── src/
```

### 設計原則

* **階段一只增不刪。** 任何刪除或搬移都要經過你逐項核准。
* **沒發現問題就不製造往返。** 整併檢查乾淨時直接給第一句話，不會為了走完流程多問你一次。
* **搬移不做價值判斷。** 從 `CLAUDE.md` 搬內容時一字不漏，不會替你決定哪段「沒價值」。
* **狀態快照不會被短對話洗掉。** `CURRENT_STATE.md` 每次覆寫，但本次沒進展的段落會保留上一版內容，且舊版一律先存進 `states/`。
* **寧可漏報也不要誤報。** 封存候選必須有具體證據（對話中講過、或 grep 零引用），不准為了湊數而列。
* **寫完回讀。** 不把「指令沒報錯」當成寫入成功；封存後要做反向檢查 —— 不是確認該搬的搬了，而是確認不該動的都還在。

### 安裝

```bash
git clone https://github.com/allenphant/wrap-up.git
cd wrap-up
./install.sh              # 繁體中文版（預設）
./install.sh --lang en    # 英文版
./install.sh --hooks      # 選用：另外安裝 70% context hook（預設不安裝）
```

`install.sh` 會建立 symlink 指向 repo 內的 skill 目錄：

```
~/.claude/skills/wrap-up  ->  <repo>/skills/zh-TW/wrap-up
~/.codex/skills/wrap-up   ->  <repo>/skills/zh-TW/wrap-up
```

這樣兩個工具共用同一份檔案，`git pull` 之後兩邊同時更新，不會有一邊忘了同步。

> **注意：這裡的 symlink 是安全且刻意的。** 前面警告過的 symlink 問題只適用於專案裡的 `CLAUDE.md` / `AGENTS.md` 指標檔 —— 因為技能會寫入那兩個檔。技能自己的安裝目錄是唯讀的，用 symlink 完全沒問題，也是推薦做法。
>
> 不想用 symlink 的話直接複製也可以：
> ```bash
> cp -r skills/zh-TW/wrap-up ~/.claude/skills/
> cp -r skills/zh-TW/wrap-up ~/.codex/skills/
> ```

### 建議用法：邊做邊寫，壓縮交給 auto compact

決策確認、任務完成、踩到會再犯的坑時，當場更新 `CURRENT_STATE.md`（把這條規則寫進你的 `AGENTS.md`）；context 壓縮交給工具內建的 auto compact；`/wrap-up` 在你想整併規則與封存舊內容時手動執行。

### 選用：70% context hook

上面的建議用法不需要 hook。想讓 Claude Code 與 Codex 在 context 使用量達到 70% 時自動要求執行 wrap-up，加上 `--hooks`（只裝一邊用 `--claude-hook` 或 `--codex-hook`）：

```bash
./install.sh --hooks
```

兩邊的語意相同：預設閾值 70%（環境變數 `WRAP_UP_CONTEXT_THRESHOLD` 可改）、每個 context window 只觸發一次、compact 之後重置、任何錯誤（壞 JSON、缺欄位、檔案不存在、例外）一律放行。觸發時 hook 在 `Stop` 事件回 `decision: block`，讓模型在這一輪結束前先跑 wrap-up。每次呼叫都會在 `~/.local/state/wrap-up/context-hook.log` 留下一行只含 metadata 的診斷紀錄（不記 prompt、不記訊息內容），方便分辨「hook 沒被呼叫」和「被呼叫但條件不符」。

**Codex**：`Stop` 事件讀取 transcript 尾端最新的 `token_count`，計算 `input_tokens / model_context_window`。安裝後在 Codex 執行 `/hooks`，審核並信任這個 hook。

**Claude Code**：hook 輸入本身沒有 context 用量（實測於 2.1.278，對照 binary 內的 hook schema：共同欄位只有 `session_id`、`transcript_path`、`cwd`、`prompt_id`、`permission_mode`、`agent_id`、`agent_type`、`effort`），transcript 也沒有 context window 大小。官方唯一有 context 百分比的結構化資料是送進 `statusLine.command` 的 JSON（`context_window`：`context_window_size` 與 `total_input_tokens = input + cache_creation + cache_read`，`used_percentage` 就是兩者相除）。安裝器因此把 statusLine 包一層 relay，並掛三個 hook：

```
Claude Code ──statusLine JSON────► claude-statusline-relay.py
                                     │  1. 寫 ~/.local/state/wrap-up/claude-context-<session>.json
                                     │     （只存 session_id、版本、模型、context_window）
                                     └─ 2. 原封轉交給你原本的 statusLine 指令，畫面不變
Claude Code ──UserPromptSubmit────► claude-context-wrap-up.py
                                     │  快照此時是新的：≥ 70% 且未觸發過 → additionalContext
                                     │  「先跑 /wrap-up 再處理這個 prompt」
Claude Code ──Stop────────────────► claude-context-wrap-up.py
                                     │  取快照與 transcript 尾端 assistant usage 的較大值：
                                     │  ≥ 70% 且未觸發過 → decision: block，這一輪結束前先 wrap-up
Claude Code ──SessionStart(compact)► 清掉觸發狀態與舊快照，下一個 window 可再觸發
```

為什麼要兩個事件：實測於 2.1.278，`Stop` 觸發時 statusLine 快照與 transcript 都還停在**上一輪**（快照在 Stop 之後 10–50 秒才更新；transcript 的 assistant 記錄在 Stop hook 跑完之後才落盤）。所以 `Stop` 只在「回合中途已經跨過閾值」（例如一個很長的工具呼叫回合）時能立刻攔下；剩下的情況由下一次 `UserPromptSubmit` 補上，那時兩個來源都是新的。兩個事件共用同一份觸發狀態，只會有一個發聲。

`~/.claude/settings.json` 修改前會先備份成 `settings.json.bak-wrap-up-<時間>`，用暫存檔＋rename 原子寫入，既有的 hooks 與其他設定全部保留，重跑安裝不會重複加入。原本的 `statusLine` 物件存在 `~/.local/state/wrap-up/claude-statusline-upstream.json`；要移除時執行：

```bash
python3 hooks/install_claude_hook.py --uninstall \
  --hook hooks/claude-context-wrap-up.py --relay hooks/claude-statusline-relay.py
```

安裝後不需要重啟：實測於 2.1.278，正在執行的 session 會自動重新讀取 `settings.json`（安裝後一分鐘內，既有 session 的 `Stop` 就已經呼叫這個 hook、狀態列也已經走 relay）。若你的版本沒有這樣做，重啟 session 或用 `/hooks` 重新載入即可。

Claude 側的限制，寫清楚：

* 只在有 statusLine 的互動式 TUI 才會運作；`claude -p` 不跑 statusLine，永遠不會觸發。
* 最壞情況晚一輪：一個回合把用量從 69% 推到 75%，`Stop` 看到的還是 69%，要等你送下一個 prompt 時 `UserPromptSubmit` 才要求 wrap-up（在處理你的 prompt 之前）。
* 必須包住你既有的 statusLine 指令。沒有 statusLine 的話 relay 會印一行最簡狀態列 `[模型] · ctx N%`。
* `Stop` 的 `decision: block` 會受 Claude Code 的 block 上限保護（`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`）；hook 也會檢查 `stop_hook_active`，續作那一輪不會再 block。`UserPromptSubmit` 只注入 context，不會擋掉你的 prompt。
* 只能宣稱「實測於 Claude Code 2.1.278 有此行為」（fixture 裡的 statusLine JSON 側錄自 2.1.274）。

### 使用

在 Claude Code 或 Codex 裡輸入：

```
/wrap-up
```

或直接說「幫我 wrap-up」「收尾一下」「做個狀態快照」。清單列出變更前後內容，接著跳出選單：可一鍵全部核准、全部不核准，或逐項勾選，之後就會拿到下一個 session 的第一句話。

### 測試

symlink 防護、「搬移不做價值判斷」、「階段一只增不刪」這些都是**用散文寫給模型看的**，不是程式強制的。所以每次改動 `SKILL.md` 都應該重跑行為測試：

```bash
./tests/selftest.sh
```

六條測試：一條是不呼叫模型的靜態檢查（中英文 `SKILL.md` 都保有核准選單規則），其中兩條會用 `--session-id` / `--resume` 跑真正的兩回合對話，驗證階段切分。測試全程在暫存目錄操作，不會碰到任何真實專案。

context hook 的可執行自測（fixture 取自真實側錄的 payload（路徑與名稱已換成示意值），不是手寫的）：

```bash
python3 tests/test_context_hook.py          # Codex：首次觸發、重複不觸發、compact 後再觸發、錯誤輸入放行、安裝 idempotent
python3 tests/test_claude_context_hook.py   # Claude Code：同上，另加 relay 轉交、他 session 不觸發、settings.json 備份／保留／還原
```

### 授權

MIT

---

## English

### What this solves

When a session ends, two kinds of value are usually left on the floor: **the preferences you stated** ("put tests in tests/ from now on") and **where the project actually stands** (what's done, what's blocked, which approach turned out to be a dead end). The first is scattered through the conversation and gone by the next session; the second only exists in your head.

`wrap-up` writes each into its own file, and solves a problem that often goes unnoticed: **Claude Code and Codex each have their own memory file (`CLAUDE.md`, `AGENTS.md`)**. Maintaining one of each guarantees drift, so this skill uses a single source of truth plus a pointer:

```
AGENTS.md      ← single source of truth; every rule lives here
CLAUDE.md      ← one line, "@AGENTS.md", redirecting Claude to the file above
```

Claude Code reads `CLAUDE.md`, sees `@AGENTS.md` and expands the import; Codex reads `AGENTS.md` directly. Both get the same ruleset, and switching a project between the two tools needs no manual step.

> This is measured, not assumed. On Claude Code 2.1.278, a lone `AGENTS.md` is read, but as soon as a `CLAUDE.md` that does not import it exists, `AGENTS.md` is ignored. A pointer `CLAUDE.md` holding the single line `@AGENTS.md` prevents that (it also covers 2.1.252, where a lone `AGENTS.md` was not read). The Codex side was verified on codex-cli 0.152.1. Nested memory files in subdirectories behave the same way.

### How a run is structured: two phases

```
you type /wrap-up
       │
       ▼
┌─ Phase 1 (no questions asked) ───────────────┐
│  1. append new preferences to AGENTS.md      │
│  2. check / repair the CLAUDE.md pointer     │
│  3. save the old CURRENT_STATE.md to states/ │
│  4. write the new CURRENT_STATE.md           │
│  5. list archive candidates — list only      │
└──────────────────────────────────────────────┘
       │
       ├─ nothing found ───────────► opening line right away (done)
       │
       ▼  approval menu in the same turn; you tick items
┌─ Phase 2 (after the menu is answered) ───────┐
│  6. apply only what you approved             │
│  7. read back and verify                     │
│  8. give the opening line for next session   │
└──────────────────────────────────────────────┘
```

**Why the writes don't wait for your approval**: the entire point of wrap-up is to make context durable before the session dies. If every output waited on your reply, anyone who runs `/wrap-up` and closes the terminal would save nothing. So **purely additive work happens immediately; only deletions and moves need approval**.

### Archiving: how AGENTS.md stays small

`AGENTS.md` is loaded into **every** session. Each stale line bills you tokens forever. But deleting it loses the context.

Archiving solves both: the content moves to `docs/wrap-up/`, where it is **never loaded**, yet stays on disk, greppable and restorable. Nothing is deleted — it is moved out of the context window.

```
project-root/
├── AGENTS.md                     ← loaded every session; kept lean
├── CLAUDE.md                     ← one-line pointer
├── CURRENT_STATE.md              ← latest state
└── docs/wrap-up/
    ├── ARCHIVE.md                ← archived rules verbatim + every move logged
    ├── states/
    │   ├── 2026-09-02-1134.md    ← past state snapshots (automatic, no approval)
    │   └── 2026-09-04-0912.md
    └── files/
        └── docs/old-design.md    ← archived files, original relative path preserved
```

**Two classes of archive target**

| Target | Criteria | Approval |
|---|---|---|
| Rules inside `AGENTS.md` | duplication / contradiction / staleness | ✅ required |
| Documents and data files | the conversation said it's obsolete, or zero references in the repo **and** the name carries `old` / a date / `deprecated` | ✅ required |
| The previous `CURRENT_STATE.md` | saved automatically before each overwrite | ❌ not required (preservation, not deletion) |

**Approval needs evidence.** Every proposed file comes with a reference count **actually obtained from `grep -rl`**, so you can tell whether moving it breaks an import or a build. The skill is not allowed to guess that number.

**The one hard limit**: `AGENTS.md`, `CLAUDE.md` and `CURRENT_STATE.md` can never be archived, and neither can anything already under `docs/wrap-up/`. That would break the mechanism outright.

**Files keep their original relative path** (`docs/old-design.md` → `docs/wrap-up/files/docs/old-design.md`), moved with `git mv` in a git repo so history survives, and logged in `ARCHIVE.md` as `original path → archive path`. Restoring is unambiguous.

### What each run does to your file tree

**Case A — brand new project**

```
before                        after
my-project/                   my-project/
└── src/                      ├── AGENTS.md          ← created: preferences from this session
                              ├── CLAUDE.md          ← created: the single line @AGENTS.md
                              ├── CURRENT_STATE.md   ← created: state snapshot
                              └── src/
```

**Case B — existing project with only CLAUDE.md (the common migration)**

```
before                        after
my-project/                   my-project/
├── CLAUDE.md  (200 lines)    ├── AGENTS.md          ← the 200 lines, verbatim, plus new preferences
└── src/                      ├── CLAUDE.md          ← replaced by the single line @AGENTS.md
                              ├── CURRENT_STATE.md   ← created
                              └── src/
```

**Case C — CLAUDE.md contaminated by another tool** (`/init` overwrote it, or another agent appended rules)

```
before                        after
my-project/                   my-project/
├── AGENTS.md  (rules)        ├── AGENTS.md          ← original + everything extra, word for word
├── CLAUDE.md  (@AGENTS.md    ├── CLAUDE.md          ← restored to the single line
│              + 3 new rules) ├── CURRENT_STATE.md
└── src/                      └── src/
```

**Case D — the dangerous shape: CLAUDE.md is a symlink**

```
before                        after
my-project/                   my-project/
├── AGENTS.md  (rules)        ├── AGENTS.md          ← untouched
├── CLAUDE.md -> AGENTS.md    ├── CLAUDE.md          ← symlink removed, replaced by a real file
└── src/                      ├── CURRENT_STATE.md
                              └── src/
```

> **Why the symlink must go**: writing through a symlink writes to its target. If the skill wrote the pointer line into that link, the entire `AGENTS.md` would be overwritten with `@AGENTS.md` and become a self-referencing import — every rule gone. The skill therefore checks for symlinks before touching anything, `rm`s the link itself (which does not affect the target), and writes a real file.

**Case E — steady state, and you approved one archive**

```
before                          after
my-project/                     my-project/
├── AGENTS.md  (3 duplicates)   ├── AGENTS.md              ← approved rule removed (verbatim in ARCHIVE.md)
├── CLAUDE.md  (@AGENTS.md)     ├── CLAUDE.md              ← unchanged
├── CURRENT_STATE.md            ├── CURRENT_STATE.md       ← overwritten; stale sections carried forward
├── docs/                       ├── docs/
│   └── old-design.md           │   └── wrap-up/
└── src/                        │       ├── ARCHIVE.md     ← rule verbatim + move log
                                │       ├── states/2026-09-04-0912.md
                                │       └── files/docs/old-design.md
                                └── src/
```

### Design principles

* **Phase 1 is append-only.** Every deletion or move waits for your item-by-item approval.
* **No round-trip when there's nothing to say.** If the consolidation check is clean, you get the opening line immediately.
* **Moving content involves no value judgement.** Content moved out of `CLAUDE.md` goes verbatim; the skill will not decide which parts are worth keeping.
* **A short session can't erase your state.** `CURRENT_STATE.md` is overwritten each run, but sections with no progress carry forward — and the old version is always saved to `states/` first.
* **Under-report rather than over-report.** Archive candidates need concrete evidence (named in the conversation, or zero grep hits). Padding the list is forbidden.
* **Read back after writing.** "The command didn't error" is not proof. After archiving, the check runs in reverse — not "did the right things move" but "is everything that shouldn't have moved still there".

### Install

```bash
git clone https://github.com/allenphant/wrap-up.git
cd wrap-up
./install.sh              # Traditional Chinese (default)
./install.sh --lang en    # English
./install.sh --hooks      # Optional: also install the 70% context hooks (off by default)
```

`install.sh` creates symlinks pointing at the skill directory inside the repo:

```
~/.claude/skills/wrap-up  ->  <repo>/skills/en/wrap-up
~/.codex/skills/wrap-up   ->  <repo>/skills/en/wrap-up
```

Both tools then share one file, and a `git pull` updates both at once — no chance of one side going stale.

> **Note: this symlink is safe and deliberate.** The symlink hazard described above applies only to the `CLAUDE.md` / `AGENTS.md` pointer files inside your projects, because the skill writes to those. The skill's own install directory is read-only, so a symlink is fine here — and is the recommended setup.
>
> If you'd rather copy:
> ```bash
> cp -r skills/en/wrap-up ~/.claude/skills/
> cp -r skills/en/wrap-up ~/.codex/skills/
> ```

### Recommended flow: write as you go, let auto compact handle compression

Update `CURRENT_STATE.md` the moment a decision is confirmed, a task is finished or a repeatable pitfall shows up (put that rule in your `AGENTS.md`). Leave context compression to the tool's built-in auto compact, and run `/wrap-up` by hand when you want to consolidate rules and archive old content.

### Optional: the 70% context hook

The recommended flow above needs no hook. To have Claude Code and Codex automatically request a wrap-up when context usage reaches 70%, add `--hooks` (or `--claude-hook` / `--codex-hook` for one side only):

```bash
./install.sh --hooks
```

Both sides share the same semantics: 70% threshold by default (override with `WRAP_UP_CONTEXT_THRESHOLD`), at most one trigger per context window, reset after compaction, and fail-open on every error (bad JSON, missing fields, missing files, exceptions). When it fires, the hook answers the `Stop` event with `decision: block` so the model runs wrap-up before the turn ends. Every invocation appends one metadata-only line to `~/.local/state/wrap-up/context-hook.log` (no prompt or message text), so "the hook was never called" and "it was called but the condition didn't match" are distinguishable.

**Codex**: the `Stop` hook reads the latest `token_count` from the tail of the transcript and computes `input_tokens / model_context_window`. After installation, run `/hooks` in Codex to review and trust the hook.

**Claude Code**: hook input carries no context usage (verified on 2.1.278 against the hook schema inside the binary: the common fields are `session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `agent_id`, `agent_type` and `effort`), and the transcript never records the context window size. The only official structured source is the JSON Claude Code pipes into `statusLine.command` (`context_window`: `context_window_size` and `total_input_tokens = input + cache_creation + cache_read`; `used_percentage` is their ratio). The installer therefore wraps the status line with a relay and registers three hooks:

```
Claude Code ──statusLine JSON────► claude-statusline-relay.py
                                     │  1. writes ~/.local/state/wrap-up/claude-context-<session>.json
                                     │     (session_id, version, model and context_window only)
                                     └─ 2. forwards the untouched payload to your previous statusLine command
Claude Code ──UserPromptSubmit────► claude-context-wrap-up.py
                                     │  snapshot is fresh here: ≥ 70% and not yet fired → additionalContext
                                     │  "run /wrap-up before working on this prompt"
Claude Code ──Stop────────────────► claude-context-wrap-up.py
                                     │  max(snapshot, latest assistant usage in the transcript tail):
                                     │  ≥ 70% and not yet fired → decision: block, wrap-up before the turn ends
Claude Code ──SessionStart(compact)► clears the trigger state and the stale snapshot for the next window
```

Why two events: measured on 2.1.278, when `Stop` fires both the statusLine snapshot and the transcript still describe the **previous** turn (the snapshot refreshes 10–50 s after Stop; the assistant record is flushed to the transcript after the Stop hooks finish). So `Stop` can only intercept immediately when the threshold was crossed mid-turn (e.g. a long tool-calling turn); every other case is caught by the next `UserPromptSubmit`, when both sources are current. The two events share one trigger state, so only one of them speaks.

`~/.claude/settings.json` is backed up to `settings.json.bak-wrap-up-<stamp>` first, written atomically via temp file + rename, and every existing hook and setting is preserved; re-running the installer adds nothing twice. The previous `statusLine` object is stored in `~/.local/state/wrap-up/claude-statusline-upstream.json`. To remove:

```bash
python3 hooks/install_claude_hook.py --uninstall \
  --hook hooks/claude-context-wrap-up.py --relay hooks/claude-statusline-relay.py
```

No restart is needed: measured on 2.1.278, running sessions re-read `settings.json` on their own (within a minute of installing, an existing session's `Stop` had already called this hook and its status line was already going through the relay). If your version does not, restart the session or reload with `/hooks`.

Claude-side limitations, stated plainly:

* Only interactive TUI sessions with a status line are covered; `claude -p` never renders the status line, so it never triggers.
* Worst case is one turn late: if a turn pushes usage from 69% to 75%, `Stop` still sees 69%, and the wrap-up request arrives with your next prompt via `UserPromptSubmit` (before that prompt is handled).
* Your existing statusLine command must be wrapped. Without one, the relay prints a minimal `[model] · ctx N%` line.
* The `Stop` block is bounded by Claude Code's block cap (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`); the hook also honours `stop_hook_active`, so the continuation turn is never blocked again. `UserPromptSubmit` only injects context and never blocks your prompt.
* Verified on Claude Code 2.1.278 only (the statusLine JSON fixture was captured on 2.1.274).

### Usage

In Claude Code or Codex:

```
/wrap-up
```

Or just say "wrap up", "close this out", "take a state snapshot". The list shows each change as before/after, then a menu lets you approve all, approve none, or pick item by item, and you get the opening line for the next session.

### Tests

The symlink guard, the no-filtering rule and the append-only phase boundary are **prose instructions to a model**, not enforced by code. So re-run the behavioral tests whenever `SKILL.md` changes:

```bash
./tests/selftest.sh
```

Six tests: one is a static check that calls no model (both `SKILL.md` files keep the approval-menu rules), and two of the others drive a real two-turn conversation with `--session-id` / `--resume` to verify the phase boundary. Everything runs in temporary directories; no real project is touched.

Executable self-tests for the context hooks (fixtures come from real captured payloads (paths and names replaced with placeholders), not hand-written):

```bash
python3 tests/test_context_hook.py          # Codex: first trigger, no repeat, re-trigger after compact, bad input passes, idempotent install
python3 tests/test_claude_context_hook.py   # Claude Code: the same, plus relay forwarding, foreign-session isolation, settings.json backup/preserve/restore
```

### License

MIT
