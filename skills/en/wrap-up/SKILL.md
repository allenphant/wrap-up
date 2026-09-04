---
name: wrap-up
description: Triggers when the user asks to wrap up, close out a session, take a state snapshot, or prepare a handover. Enforces project state updates, preference capture, and archiving of stale content.
---
You have been triggered by the `wrap-up` skill.

This skill runs in two phases. **Phase 1 needs no confirmation — do all of it directly.** Phase 2 runs only after I reply.

**"Project root" in this skill means**: the directory containing the `AGENTS.md` / `CLAUDE.md` actually loaded for this session. If neither exists, use the current working directory. Do not create these files in a parent directory or anywhere else.

**Archive location**: `docs/wrap-up/` under the project root (create it if missing).

---

# Phase 1: write immediately, then propose a review list

Do 1-1 through 1-4 without asking me anything. After 1-5, stop and wait for my reply.

## 1-1 Update project preferences (AGENTS.md)

Review this conversation. If I (the user) stated any new "general development preference, code style requirement, or specific habit" (e.g. a required library, a particular way of writing something), **append** those rules to `AGENTS.md` in the project root.

* Create `AGENTS.md` if it does not exist.
* **⚠️ This phase may only add. Never delete or rewrite existing content here.** Every removal or edit waits for Phase 2, after I approve it.
* After writing, **read back the tail of the file** to confirm the content actually landed. "The command did not error" is not proof.
* If this conversation produced no new preferences, skip the write — but still do everything from 1-2 onward.

## 1-2 Pointer-file maintenance (check every time)

`AGENTS.md` is the single source of truth. However, Claude Code only reads `CLAUDE.md` and does **not** discover `AGENTS.md` automatically (verified on Claude Code 2.1.252). The project root therefore needs a `CLAUDE.md` whose content is **only** this single line:

```
@AGENTS.md
```

(Tools that read `AGENTS.md` natively, such as Codex, do not need this file. It exists purely for Claude Code compatibility and is harmless to everything else.)

Work through these in order:

1. **Check for symlinks first.** Use `ls -la` or `stat` to determine whether `CLAUDE.md` or `AGENTS.md` is a symlink.
   If either one is, **`rm` the symlink itself first** (removing a link does not touch its target), then write the intended content as a regular file.
   **Never write through a symlink** — writing to the link writes to its target, which would overwrite the entire ruleset with a single line and turn it into a self-referencing import.
2. `CLAUDE.md` does not exist → create it containing that single line.
3. `CLAUDE.md` exists but holds more than that line (overwritten by `/init`, or appended to by another agent) →
   **first append everything extra to `AGENTS.md` verbatim, word for word**, read back to confirm the move completed, and only then overwrite `CLAUDE.md` with that single line.
   **Do not decide for yourself which parts are "worth keeping" and drop the rest** — a wrong call silently deletes rules someone else wrote.
4. **Never write the rules themselves into `CLAUDE.md`** — that creates a second copy that will drift.

## 1-3 Archive the previous state snapshot

If `CURRENT_STATE.md` already exists, **copy it to** `docs/wrap-up/states/YYYY-MM-DD-HHMM.md` first (use the timestamp recorded inside that file; fall back to its mtime).

This step **needs no approval** — it preserves, it does not delete. Without it, the next step's overwrite throws the history away.

## 1-4 Update the project state snapshot (CURRENT_STATE.md)

Update (or create) `CURRENT_STATE.md` in the project root, **overwriting** it so the project keeps exactly one current-state document.

**Read the existing content first.** If a section saw no progress in this conversation (no failed attempts this time, no new decisions), **carry forward the previous version's content for that section**. Do not write "none" or drop it — otherwise one short conversation erases context accumulated over weeks.

Use this Markdown structure strictly, and keep it distilled:

# [One-line summary: what is being worked on + current status (done / in progress / blocked), written like a git commit message]

> **Updated**: YYYY-MM-DD HH:MM
> **Project core**: one line on the project's goal and main tech stack

## Goal of this session

(What this conversation set out to accomplish)

## Completed

* **[Task]**: (summary of the key changes)
  * `path/to/changed/file1`
  * `path/to/changed/file2`

## In Progress & Blockers

* **Current progress**: (how far it got)
* **Next step**: (what comes next)
* **Blocker**: (what is stuck and why; write "none" if nothing)

## Failed Approaches

* **What was tried**: (the concrete approach)
  * **Why it failed**: (the error or the logical flaw)
  * **Lesson**: (never go down this road again)

## Key Decisions

* **[Decision]**: (what was decided, e.g. database choice, architecture)
  * **Rationale**: (why)
  * **Rejected alternatives**: (what was not chosen)

## Handover Context

(Written for the next AI entity with zero prior context. Include the current technical picture, and the first command you strongly recommend it run — or the first file it should read.)

## 1-5 Produce the review list (list only — change nothing)

Examine two classes of target. **In this phase you may not edit a single word or move a single file.**

### Class A: rules inside `AGENTS.md`

1. **Duplication** — the same rule stated more than once in different words, or several headings covering the same ground.
2. **Contradiction** — two rules that conflict (one says "always use X", another says "never use X").
3. **Staleness** — a rule referring to a file, command, tool, or version that no longer exists or has been superseded.

### Class B: stale documents and data files in the project

**Only report something when you have concrete evidence.** It must meet one of these:

* This conversation explicitly said it is obsolete, superseded, or no longer maintained; or
* Nothing in the repository references it (confirm with `grep -rl <filename>`), **and** its name carries a date, `old`, `legacy`, `deprecated`, `backup`, `_bak`, `archive`, or an obvious successor version exists.

**Do not pad the list**, and do not report things you merely suspect are unused. Under-reporting beats over-reporting.

### List format

For every item, give:

* **Location** — line range in `AGENTS.md`, or the file's relative path
* **Class** — duplication / contradiction / staleness
* **Evidence** — for a contradiction, name the rule it conflicts with; for a file, include `references in repo: N` (a number you actually got from grep, never a guess)
* **Proposed action** — where it would be archived to
* **Reason** — one sentence

### Then stop

Once the list is out, **stop and wait for my reply. Do not give the opening line for the next session in this phase.**

**If neither class turns up anything**: say "consolidation check: nothing to report", **skip Phase 2, and give me the opening line immediately** (format at the end of Phase 2). Do not manufacture a round-trip just to complete the ritual.

---

# Phase 2: apply what I approved, then give the opening line

Run this only after I reply.

1. **Act only on items I explicitly approved.** Anything I did not mention, did not answer, or was unsure about **stays exactly as it is**.
2. **Archiving a rule**: write the passage **verbatim, word for word** into `docs/wrap-up/ARCHIVE.md` (append, with the archive date, class, and origin). **Confirm the write and read it back**, and only then remove that passage from `AGENTS.md`.
3. **Archiving a file**: move it to `docs/wrap-up/files/<original relative path>`, **preserving the directory structure** (e.g. `docs/old-design.md` → `docs/wrap-up/files/docs/old-design.md`) so restoring it is unambiguous.
   * Use `git mv` when the repo is a git repository, to keep the file's history.
   * Log every move in `ARCHIVE.md`: `original path → archive path`, date, reason.
4. **Never archive `AGENTS.md`, `CLAUDE.md`, or `CURRENT_STATE.md` themselves**, and never archive anything already under `docs/wrap-up/`. Doing so breaks the whole mechanism.
5. **The first time an archive is created**, append one line to `AGENTS.md` (once only — never repeat it on later runs):
   `> Archived rules and documents live in docs/wrap-up/ARCHIVE.md.`
6. After all edits, **read back and verify** — confirm what should have moved did, and that **everything that should not have moved is still there**.
7. Update the timestamp in `CURRENT_STATE.md` and add a line under "Completed" recording what was archived.
8. Give me the opening line (below).

**If I reply "leave it all", answer something unrelated, or approve nothing** — change nothing and go straight to the opening line. Do not press me, do not stall.

### The opening line

Finally, briefly tell me which files you updated, whether you added rules to `AGENTS.md`, and what was archived. Then give me the exact opening line I can paste into the next conversation. For example:

> Read `/absolute/path/to/CURRENT_STATE.md` to catch up; next we're going to…

Give the **absolute path** to `CURRENT_STATE.md`.
