# wrap-up

一個給 Claude Code 與 Codex 共用的收尾技能：把散落在對話裡的偏好與狀態，固定寫進兩個工具都讀得到的檔案，並把過時的內容封存起來而不是刪掉。

A session wrap-up skill shared by Claude Code and Codex: it captures the preferences and state buried in a conversation into files both tools can read, and archives what has gone stale instead of deleting it.

[繁體中文](#繁體中文) · [English](#english)

---

## 繁體中文

### 這個技能解決什麼問題

對話結束時，有價值的東西通常有兩種：**你講過的偏好**（「以後測試都放 tests/」）和**專案現在的狀態**（做到哪、卡在哪、哪條路走不通）。前者散在對話裡，下一個 session 就忘了；後者只存在你腦中。

`wrap-up` 把這兩件事各自寫成一個檔案，並且解決一個常被忽略的問題：**Claude Code 只讀 `CLAUDE.md`，Codex 只讀 `AGENTS.md`**。兩邊各寫一份必然走樣，所以這個技能採用單一真相來源 + 指標檔：

```
AGENTS.md      ← 唯一真相來源，所有規則都在這
CLAUDE.md      ← 只有一行 "@AGENTS.md"，把 Claude 導向上面那份
```

Claude Code 讀 `CLAUDE.md`，看到 `@AGENTS.md` 就展開匯入；Codex 直接讀 `AGENTS.md`。兩邊拿到同一份規則，專案在兩個工具間切換不需要任何手動動作。

> 這是實測結論，不是推論。Claude Code 2.1.252 在只有 `AGENTS.md` 的目錄裡讀不到內容（canary 測試回答 UNKNOWN），加上一行 `@AGENTS.md` 的 `CLAUDE.md` 後即讀得到。Codex 側實測於 codex-cli 0.152.1。子目錄的巢狀記憶檔同樣適用。

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
       ▼  停下來等你回覆
┌─ 階段二（你回覆之後）────────────────────────┐
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

### 使用

在 Claude Code 或 Codex 裡輸入：

```
/wrap-up
```

或直接說「幫我 wrap-up」「收尾一下」「做個狀態快照」。看到封存清單後，回覆哪幾項可以動（或「都不用改」），就會拿到下一個 session 的第一句話。

### 測試

symlink 防護、「搬移不做價值判斷」、「階段一只增不刪」這些都是**用散文寫給模型看的**，不是程式強制的。所以每次改動 `SKILL.md` 都應該重跑行為測試：

```bash
./tests/selftest.sh
```

五條測試，其中兩條會用 `--session-id` / `--resume` 跑真正的兩回合對話，驗證階段切分。測試全程在暫存目錄操作，不會碰到任何真實專案。

### 授權

MIT

---

## English

### What this solves

When a session ends, two kinds of value are usually left on the floor: **the preferences you stated** ("put tests in tests/ from now on") and **where the project actually stands** (what's done, what's blocked, which approach turned out to be a dead end). The first is scattered through the conversation and gone by the next session; the second only exists in your head.

`wrap-up` writes each into its own file, and solves a problem that often goes unnoticed: **Claude Code only reads `CLAUDE.md`, Codex only reads `AGENTS.md`**. Maintaining one of each guarantees drift, so this skill uses a single source of truth plus a pointer:

```
AGENTS.md      ← single source of truth; every rule lives here
CLAUDE.md      ← one line, "@AGENTS.md", redirecting Claude to the file above
```

Claude Code reads `CLAUDE.md`, sees `@AGENTS.md` and expands the import; Codex reads `AGENTS.md` directly. Both get the same ruleset, and switching a project between the two tools needs no manual step.

> This is measured, not assumed. On Claude Code 2.1.252, a directory containing only `AGENTS.md` yields nothing (a canary test answers UNKNOWN); adding a `CLAUDE.md` holding the single line `@AGENTS.md` makes it readable. The Codex side was verified on codex-cli 0.152.1. Nested memory files in subdirectories behave the same way.

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
       ▼  stop and wait for your reply
┌─ Phase 2 (after you reply) ──────────────────┐
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

### Usage

In Claude Code or Codex:

```
/wrap-up
```

Or just say "wrap up", "close this out", "take a state snapshot". When the archive list comes back, reply with which items to act on (or "leave it all") and you get the opening line for the next session.

### Tests

The symlink guard, the no-filtering rule and the append-only phase boundary are **prose instructions to a model**, not enforced by code. So re-run the behavioral tests whenever `SKILL.md` changes:

```bash
./tests/selftest.sh
```

Five tests; two of them drive a real two-turn conversation with `--session-id` / `--resume` to verify the phase boundary. Everything runs in temporary directories; no real project is touched.

### License

MIT
