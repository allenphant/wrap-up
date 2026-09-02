---
name: wrap-up
description: Triggers when the user asks to wrap up, close out a session, take a state snapshot, or prepare a handover. Enforces project state updates and preference capture.
---
You have been triggered by the `wrap-up` skill. Execute the following two steps directly; do not ask me for confirmation.

**"Project root" in this skill means**: the directory containing the `AGENTS.md` / `CLAUDE.md` actually loaded for this session. If neither exists, use the current working directory. Do not create these files in a parent directory or anywhere else.

### Step 1: Update project preferences (AGENTS.md)

Review this conversation. If I (the user) stated any new "general development preference, code style requirement, or specific habit" (e.g. a required library, a particular way of writing something), **append** those rules to `AGENTS.md` in the project root.

* If `AGENTS.md` does not exist, create it.
* **⚠️ Never delete or overwrite existing content in `AGENTS.md` without the user's confirmation.** The default behavior is append-only.
* After writing, **read back the tail of the file** to confirm the content actually landed. Do not treat "the command did not error" as success.
* If this conversation produced no new preferences, skip the write — but **still perform the consolidation check and pointer-file maintenance below**.

#### Consolidation check (run after appending; keeps AGENTS.md from growing without bound)

Scan the whole of `AGENTS.md` for three classes of problem:

1. **Duplication** — the same rule stated more than once in different words, or several headings covering the same ground.
2. **Contradiction** — a new rule conflicting with an existing one (e.g. the new one says "always use X", the old one says "never use X").
3. **Staleness** — a rule referring to a file, command, tool, or version that no longer exists or has been superseded.

**Never delete or edit anything on your own initiative.** Present the findings as a list, and for each item state: which lines, which class, what you suggest doing, and why. Act only after the user confirms each item.

* Anything the user does not respond to, or does not explicitly approve, **stays exactly as it is**.
* When you do edit, make the smallest change to the confirmed sections only. **Do not rewrite the whole file.** Read back to verify afterwards.
* If you find nothing, just say "consolidation check: nothing to report". Do not invent findings to look useful.

#### Pointer-file maintenance (check every time, even when there are no new preferences)

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

### Step 2: Update the project state snapshot (CURRENT_STATE.md)

Update (or create) `CURRENT_STATE.md` in the project root. Every run of this command **overwrites** the file, so the project keeps exactly one current-state document.

**Read the existing `CURRENT_STATE.md` first (if it exists).** If a section saw no progress in this conversation (no failed attempts this time, no new decisions), **carry forward the previous version's content for that section**. Do not write "none" or drop it — otherwise one short conversation erases context accumulated over weeks.

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

---

When you are done, briefly tell me which files you updated, whether you added rules to AGENTS.md, the result of the consolidation check, and give me the exact opening line I can paste into the next conversation. For example: "Read `CURRENT_STATE.md` to catch up; next we're going to…" — and give me the absolute path to `CURRENT_STATE.md`.
