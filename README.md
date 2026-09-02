# wrap-up

一個給 Claude Code 與 Codex 共用的收尾技能：把散落在對話裡的偏好與狀態，固定寫進兩個工具都讀得到的檔案。

A session wrap-up skill shared by Claude Code and Codex: it captures the preferences and state buried in a conversation into files that both tools can read.

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
│              + 3 條新規則)  ├── CURRENT_STATE.md   ← 覆寫（未變動的段落保留上一版）
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

**情境 E — 穩定狀態，重複執行**

```
執行前                        執行後
my-project/                   my-project/
├── AGENTS.md                 ├── AGENTS.md          ← 只在檔尾追加（沒有新偏好就完全不動）
├── CLAUDE.md  (@AGENTS.md)   ├── CLAUDE.md          ← 不變
├── CURRENT_STATE.md          ├── CURRENT_STATE.md   ← 覆寫，但沒進展的段落保留上一版內容
└── src/                      └── src/
```

### 設計原則

* **預設只增不刪。** `AGENTS.md` 的既有內容不會被自動刪改。
* **整併需要你點頭。** 為了避免 `AGENTS.md` 無限膨脹，每次執行都會檢查重複、矛盾、過時三類問題，但**只會列清單問你**，逐項確認後才動手。沒回應的項目維持原樣。
* **搬移不做價值判斷。** 從 `CLAUDE.md` 搬內容時一字不漏，不會替你決定哪段「沒價值」。
* **狀態快照不會被短對話洗掉。** `CURRENT_STATE.md` 每次覆寫，但本次沒進展的段落會保留上一版內容。
* **寫完回讀。** 不把「指令沒報錯」當成寫入成功。

### 安裝

```bash
git clone https://github.com/<your-account>/wrap-up.git
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

或直接說「幫我 wrap-up」「收尾一下」「做個狀態快照」。

### 測試

symlink 防護和「搬移不做價值判斷」這兩條是**用散文寫給模型看的**，不是程式強制的。所以每次改動 `SKILL.md` 都應該重跑行為測試：

```bash
./tests/selftest.sh
```

測試全程在暫存目錄操作，不會碰到任何真實專案。

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
│              + 3 new rules) ├── CURRENT_STATE.md   ← overwritten (untouched sections carried forward)
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

**Case E — steady state, run again**

```
before                        after
my-project/                   my-project/
├── AGENTS.md                 ├── AGENTS.md          ← appended to only (untouched if nothing new)
├── CLAUDE.md  (@AGENTS.md)   ├── CLAUDE.md          ← unchanged
├── CURRENT_STATE.md          ├── CURRENT_STATE.md   ← overwritten; stale sections carried forward
└── src/                      └── src/
```

### Design principles

* **Append-only by default.** Existing content in `AGENTS.md` is never edited or removed automatically.
* **Consolidation needs your approval.** To keep `AGENTS.md` from growing without bound, every run checks for duplication, contradiction and staleness — but it only **presents a list**, and acts item by item after you confirm. Anything you don't answer stays as it is.
* **Moving content involves no value judgement.** When content is moved out of `CLAUDE.md` it goes verbatim; the skill will not decide which parts are worth keeping.
* **A short session can't erase your state.** `CURRENT_STATE.md` is overwritten each run, but sections with no progress carry forward from the previous version.
* **Read back after writing.** "The command didn't error" is not treated as proof the write landed.

### Install

```bash
git clone https://github.com/<your-account>/wrap-up.git
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

Or just say "wrap up", "close this out", "take a state snapshot".

### Tests

The symlink guard and the no-filtering rule are **prose instructions to a model**, not enforced by code. So re-run the behavioral tests whenever `SKILL.md` changes:

```bash
./tests/selftest.sh
```

Everything runs in temporary directories; no real project is touched.

### License

MIT
