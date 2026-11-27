---
name: wrap-up
description: When the user or a conversation hook explicitly asks to wrap up, close out, save a state snapshot, or hand over, update the project state, append new preferences, and propose an evidence-backed archive list. Merely asking about or consulting this skill's design does not trigger a wrap-up.
---

# Wrap-up

Maintain two default entry points: `AGENTS.md` holds long-lived rules and the entry points to task documents, `CURRENT_STATE.md` holds the latest handover. `CLAUDE.md` is only a compatibility pointer. Existing project specs are read as the task requires; do not add another state or decision document by default.

Two phases: Phase 1 saves directly; Phase 2 only handles the rule consolidation and document archiving the user approved. Do not ask again for something already explicitly authorized. Other work may continue; unapproved edits and removals stay pending.

## Location and boundaries

- The project root is the directory of the project-level `AGENTS.md` / `CLAUDE.md` loaded for this session; if neither exists, the current working directory. Inheriting instructions from a parent directory does not move project state up there.
- History lives under `docs/wrap-up/` in the root. Archived files are never a source of current rules or state.
- Keep the project's limits on data, secrets, and operations. Saving and handing over do not widen access, and sensitive values are never written into rules or snapshots.

## Phase 1: save directly, then propose a review list

### 1. Append new preferences

Read `AGENTS.md` first and append only long-lived preferences that the user actually added in this conversation and that are not recorded yet; if there are none, skip the write. Create the file if missing.

In this phase, do not rewrite, delete, or consolidate existing rules. Do not add execution logs, temporary blockers, the status of business topics, or preferences the agent inferred on its own. Read back after writing.

### 2. Maintain the compatibility pointer

`AGENTS.md` is the source of project rules; the entire content of `CLAUDE.md` is `@AGENTS.md` plus a newline.

1. First check whether either file is a symlink, and never write through a link. When one must become a regular file, safely read and preserve its content, remove the link itself, and create a regular file with the same content; never change the link target. If the target cannot be read or lies outside the allowed access scope, stop the operations that depend on it and report.
2. If `CLAUDE.md` does not exist, create the one-line pointer.
3. If it holds anything else, first append everything outside the pointer verbatim to `AGENTS.md`, without filtering out any rule; read back to confirm it was fully saved, then turn `CLAUDE.md` into the one-line pointer. If only the trailing newline is missing, just add it.
4. Read back to confirm both are regular files, no rule was lost, and the pointer is correct.

### 3. Save the previous state

Before overwriting, read `CURRENT_STATE.md` completely and, if it exists, copy it byte for byte to `docs/wrap-up/states/YYYY-MM-DD-HHMM.md`, using the file's recorded update time, or its mtime if there is none.

If a snapshot with that name exists with identical content, reuse it; if the content differs, save under a numbered suffix and never overwrite an existing snapshot. Read back and compare before updating the root state. If the snapshot fails, do not overwrite. If the state file is a symlink, first follow the safe preserve-and-convert procedure above.

### 4. Distill the latest state

Keep the facts that still hold; the old wording does not have to be reused. Unresolved items with no progress this time must still be kept — never write "none" or silently drop them; completed history is carried by the snapshot.

Use the six sections below with these names and this order, preceded by a one-line status title, the update time, and a one-line project core:

| Section | What to keep |
| --- | --- |
| Goal of this session | The latest working goal; if the user only adds detail or asks questions, keep the original goal. |
| Completed | A few results relevant to the current work and where the evidence is; no turn-by-turn change log. |
| In Progress & Blockers | Every unresolved item; compress old side threads to one sentence each, keeping status, the condition to resume or finish, and the evidence entry point. |
| Failed Approaches | Problems that can still recur, why, and how to avoid them. |
| Key Decisions | Summaries of the decisions later work must know, with sources where needed. |
| Handover Context | The first step for whoever takes over, the success criteria, and which documents to read for which task. |

You may use this skeleton directly, without any explanatory text in brackets:

```markdown
# [Current work and status]

> **Updated**: YYYY-MM-DD HH:MM
> **Project core**: [goal and main technology]

## Goal of this session

## Completed

## In Progress & Blockers

## Failed Approaches

## Key Decisions

## Handover Context
```

**Soft character budget: 1,500–2,500 Chinese characters' worth of content; for an English state file use about 3,000–5,000.** Count Unicode code points of the fully decoded UTF-8 text, e.g. Python `len(text)`, including headings, punctuation, spaces, newlines, Markdown, and paths — not bytes or tokens. There is no minimum to pad up to.

When over budget, first remove repetition and historical detail, merge similar side threads, and cite existing evidence. Do not truncate, or drop unresolved items, safety conditions, or decisions needed for handover, to meet the number; if it is still over, keep what is necessary and say why. Do not create parallel state files to save characters.

Detailed logs stay in run artifacts. The state keeps only conclusions, their scope, and evidence entry points; distinguish "decided", "implemented", and "verified", and never present partial verification as complete.

After writing, read back and check: the order of the six sections, the actual character count, where every unresolved item of the previous version went, the required decisions and safety conditions, and the evidence entry points added this time. An item leaves the unresolved list only when the conversation or evidence supports that it was completed, cancelled, or superseded. If a needed document is missing, record that; do not substitute a historical archive.

### 5. Propose an evidence-backed review list

Check only what relates to this work; do not read the whole project history just to build a list. This step only reports: change no rules, move no documents.

- **Class A, rules**: duplication, contradiction, or evidenced staleness in `AGENTS.md`.
- **Class B, documents**: the conversation explicitly confirmed it is obsolete, superseded, or unmaintained; or an actual search found no references and the file has a historical name or a clear successor. Searches follow the project's tool priority (`rg` is fine for non-code files). State the search scope and exclusions; "no references found" alone is not evidence of staleness.
- Never report the three core files in the root or the historical evidence under `docs/wrap-up/`, and a `legacy` name alone does not mean unused.

For each item give an ID, line numbers or relative path, class, concrete evidence, and reason, and show **Before / After** so the user never has to guess what approving does. Reference counts must come from an actual search.

- **Class A**:
  - Before: quote the exact text to be changed with its `AGENTS.md` line numbers; for a duplication or contradiction, quote the other rule too, with line numbers.
  - After: the full consolidated or corrected wording; for a removal, "removed; original moved verbatim to `docs/wrap-up/ARCHIVE.md`".
  - Effect: one sentence on whether the meaning of the rule changes (e.g. "wording merged only, scope unchanged").
- **Class B**:
  - Before: the current path, plus the reference search scope and result (`references in repo: N`, listing the matching files).
  - After: the archive path `docs/wrap-up/files/<original relative path>`; if references must be fixed, list "which file, which line, changed to what".
  - Restore: one sentence on how to move it back.

If there are no findings, report "consolidation check: nothing to report", skip Phase 2, and give the opening line.

If there are items, first print the full evidence list as text, then get approval with `AskUserQuestion` **in this same turn**; do not defer the question to the next turn. `AskUserQuestion` is a deferred tool; load it first with `ToolSearch select:AskUserQuestion`.

- **Put the overall switch and the item questions in the same call**: one call carries several questions, question 1 is always the overall switch, and question 2 onward are the item checklists. Never ask the switch alone and wait for its answer before asking the items.
- **Question 1 (overall switch, single-select)**: `question` asks "How should the N listed items be handled? With 'Approve all' or 'Approve none' you can skip the other questions and Submit." Three options:
  - "Approve all": apply **every item** in the printed list (including ones that did not fit in this call), ignore ticks in the other questions, and ask nothing further. Its `description` lists all IDs and actions as "Before: … → After: …".
  - "Use the ticks below": apply only the items ticked in the item questions.
  - "Approve none": leave everything as is, ignore ticks in the other questions, and ask nothing further.
- **Question 2 onward (item questions)**: each uses `multiSelect: true`, with separate questions for class A and class B. An option must be understandable without reading the list above:
  - `question`: a full sentence saying what approval will do, e.g. "Approving these rule and archive items changes `AGENTS.md`; the original text is first saved verbatim to `ARCHIVE.md`. Which should I apply?"
  - `label`: ID plus action and target, e.g. "A1 Remove lines 40–44 (duplicates line 12)", "B2 Archive docs/old-design.md".
  - `description`: always "Before: … → After: …", one sentence each, with concrete line numbers or paths.
  - When a question would hold only 1 item, add a "Do not apply (leave as is)" option so it has the minimum of 2 options.
- If question 1 is unanswered but items are ticked, the ticked items count as approved.
- At most 4 questions per call and 4 options per question, so the first call is the switch plus up to 3 item questions. When there are more items, order them by strength of evidence; if question 1 is "Use the ticks below", or only items were ticked, ask further rounds (item questions only) until all have been asked within this conversation; never skip an unasked item.
- Unticked, "Do not apply (leave as is)", cancelled, or no answer at all = not approved; leave as is and do not press.
- "Approve all" covers only the items printed as text before the question; anything found later needs its own approval.
- The overall switch or the ticked selection is the authorization, with IDs matching the text list; record it as "approved by the user on YYYY-MM-DD via the wrap-up menu".
- Non-interactive runs (`claude -p`, hook-triggered, and so on) cannot show the menu: stop at the list, say that this skill requires approval before editing or removing, and give no opening line.

## Phase 2: apply the approved items

1. Handle only the items covered by "Approve all" or ticked in the Phase 1 menu (or explicitly approved in text); unanswered, uncertain, or rejected items stay as they are. If nothing is approved, do not press; give the opening line.
2. **Before consolidating or removing rules**: append all text to be rewritten or removed verbatim to `docs/wrap-up/ARCHIVE.md` with date, class, origin, authorization, and reason; read back to confirm it is complete, then edit `AGENTS.md`. Keep scope and exceptions; consolidation must not change a rule's meaning.
3. **Before archiving documents**: check references and fix current entry points. Move to `docs/wrap-up/files/<original relative path>`, keeping the directory structure; use `git mv` for tracked files and a plain move for untracked ones. If the destination exists, pick a non-conflicting one without overwriting; record original path, archive path, date, and reason. External documents do not become movable or editable through this.
4. Never archive the root `AGENTS.md`, `CLAUDE.md`, or `CURRENT_STATE.md`, and never re-archive anything under `docs/wrap-up/`. Saving a copy of the previous version is not moving a root file.
5. On the first rule or document archive, add an archive entry point to `AGENTS.md` once; do not repeat an equivalent one. A README in the archive directory briefly explains its historical purpose and where the current source is; do not create parallel state.
6. Read back edits and archived content, confirm unapproved items are untouched, the pointer is intact, and references work.
7. Save the current state again under the Phase 1 snapshot rules, then update the time, relevant results, and next step in `CURRENT_STATE.md`, still using the six sections and the soft budget.

## Closing reply

Briefly state which files were updated, whether new rules were appended, what was archived, and what remains. Give an opening line that can be pasted into the next conversation, using the absolute path of `CURRENT_STATE.md`:

> Read `/absolute/path/to/CURRENT_STATE.md` to catch up, then carry out the next step in the handover notes.
