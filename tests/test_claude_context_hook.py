#!/usr/bin/env python3
"""Executable regression tests for the Claude Code context wrap-up hook.

Fixtures are real captures, not hand-written payloads:
- claude-stop-2.1.278.json / claude-session-start-startup-2.1.278.json were
  recorded from Claude Code 2.1.278 hooks via `claude -p --settings`.
- claude-statusline-2.1.274.json is the raw JSON Claude Code piped into the
  statusLine command (18% used). The *-derived-72pct.json copy only rescales
  the context numbers so the default 70% threshold is exercised; the file says
  so in `_fixture_note`.
- claude-transcript-2.1.278.jsonl holds real transcript records from an
  interactive 2.1.278 session (assistant usage, stop_hook_summary,
  compact_boundary) with message.content redacted.
The compact SessionStart payload is the real startup capture with `source`
switched to "compact"; the enum in the 2.1.278 hook schema is
startup/resume/clear/compact/fork and the live hook log confirmed
source="compact" after /compact.

Every scenario runs the actual scripts as subprocesses with WRAP_UP_STATE_DIR
pointed at a temp dir, and the snapshot the hook reads is produced by running
the relay itself, so the two never share an invented file format.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "claude-context-wrap-up.py"
RELAY = ROOT / "hooks" / "claude-statusline-relay.py"
INSTALLER = ROOT / "hooks" / "install_claude_hook.py"
FIXTURES = ROOT / "tests" / "fixtures"
STOP = json.loads((FIXTURES / "claude-stop-2.1.278.json").read_text(encoding="utf-8"))
STARTUP = json.loads(
    (FIXTURES / "claude-session-start-startup-2.1.278.json").read_text(encoding="utf-8")
)
STATUS_REAL = (FIXTURES / "claude-statusline-2.1.274.json").read_text(encoding="utf-8")
STATUS_72 = (FIXTURES / "claude-statusline-2.1.274-derived-72pct.json").read_text(
    encoding="utf-8"
)
STATUS_FRESH = (FIXTURES / "claude-statusline-2.1.274-derived-fresh.json").read_text(
    encoding="utf-8"
)
TRANSCRIPT = (FIXTURES / "claude-transcript-2.1.278.jsonl").read_text(encoding="utf-8")
SESSION = json.loads(STATUS_REAL)["session_id"]


def run(script: Path, stdin: str, state_dir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["WRAP_UP_STATE_DIR"] = str(state_dir)
    environment.pop("WRAP_UP_CONTEXT_THRESHOLD", None)
    environment.update(env)
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def stop_payload(**extra: object) -> str:
    # The captured transcript_path only exists on the machine that recorded it;
    # point at a missing file by default so scenarios stay deterministic and
    # opt into the transcript explicitly.
    value = dict(STOP, session_id=SESSION, transcript_path="/nonexistent/wrap-up-test.jsonl")
    value.update(extra)
    return json.dumps(value)


def prompt_payload(**extra: object) -> str:
    # UserPromptSubmit input = common fields + prompt (+ session_title); the
    # 2.1.278 schema has no stop_hook_active here.
    value = {key: STOP[key] for key in ("session_id", "transcript_path", "cwd", "prompt_id",
                                        "permission_mode")}
    value.update(session_id=SESSION, transcript_path="/nonexistent/wrap-up-test.jsonl",
                 hook_event_name="UserPromptSubmit", prompt="SECRET-PROMPT-TEXT do the thing")
    value.update(extra)
    return json.dumps(value)


def session_start(source: str, **extra: object) -> str:
    value = dict(STARTUP, session_id=SESSION, source=source)
    value.update(extra)
    return json.dumps(value)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_relay_and_hook(temporary_path: Path) -> None:
    state_dir = temporary_path / "state"

    # Relay without upstream: writes the snapshot and prints a fallback line.
    relayed = run(RELAY, STATUS_72, state_dir)
    check(relayed.returncode == 0, relayed.stderr)
    check("Opus 5" in relayed.stdout and "72%" in relayed.stdout, relayed.stdout)
    snapshot = json.loads((state_dir / f"claude-context-{SESSION}.json").read_text())
    check(snapshot["context_window"]["used_percentage"] == 72, str(snapshot))
    check("cost" not in snapshot and "cwd" not in snapshot, "snapshot must be metadata-only")

    # First Stop above threshold triggers exactly once.
    first = run(HOOK, stop_payload(), state_dir)
    check(first.returncode == 0, first.stderr)
    check('"decision": "block"' in first.stdout, first.stdout)
    check("/wrap-up" in first.stdout, first.stdout)
    check("72.0%" in first.stdout, first.stdout)

    duplicate = run(HOOK, stop_payload(), state_dir)
    check(duplicate.returncode == 0, duplicate.stderr)
    check(duplicate.stdout == "", duplicate.stdout)

    # The continuation turn (stop_hook_active) never re-blocks.
    active = run(HOOK, stop_payload(stop_hook_active=True), state_dir)
    check(active.returncode == 0 and active.stdout == "", active.stdout)

    # Once triggered, the next prompt does not ask again either.
    prompt_after = run(HOOK, prompt_payload(), state_dir)
    check(prompt_after.returncode == 0 and prompt_after.stdout == "", prompt_after.stdout)

    # Compact resets the state and drops the stale pre-compact snapshot.
    reset = run(HOOK, session_start("compact"), state_dir)
    check(reset.returncode == 0 and reset.stdout == "", reset.stdout)
    check(not (state_dir / f"claude-context-{SESSION}.json").exists(), "stale snapshot kept")
    stale = run(HOOK, stop_payload(), state_dir)
    check(stale.returncode == 0 and stale.stdout == "", "triggered from stale snapshot")

    # After the status line refreshes above threshold again, the next prompt
    # asks for wrap-up via additionalContext, and Stop then stays quiet.
    run(RELAY, STATUS_72, state_dir)
    again = run(HOOK, prompt_payload(), state_dir)
    parsed = json.loads(again.stdout)
    check(parsed["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit", again.stdout)
    check("/wrap-up" in parsed["hookSpecificOutput"]["additionalContext"], again.stdout)
    check("decision" not in parsed, "UserPromptSubmit must never block the prompt")
    quiet = run(HOOK, stop_payload(), state_dir)
    check(quiet.returncode == 0 and quiet.stdout == "", quiet.stdout)

    # Real capture at 18%: below the default threshold, above a lowered one.
    run(HOOK, session_start("clear"), state_dir)
    run(RELAY, STATUS_REAL, state_dir)
    below = run(HOOK, stop_payload(), state_dir)
    check(below.returncode == 0 and below.stdout == "", below.stdout)
    lowered = run(HOOK, stop_payload(), state_dir, WRAP_UP_CONTEXT_THRESHOLD="10")
    check('"decision": "block"' in lowered.stdout, lowered.stdout)
    check("17.99%" in lowered.stdout or "18.0%" in lowered.stdout, lowered.stdout)

    # A snapshot from another session never triggers this one.
    other = run(HOOK, stop_payload(session_id="some-other-session"), state_dir,
                WRAP_UP_CONTEXT_THRESHOLD="10")
    check(other.returncode == 0 and other.stdout == "", other.stdout)

    # Error inputs are let through.
    for bad in ("this is not JSON", "[1, 2, 3]", "", json.dumps({"hook_event_name": "Stop"})):
        result = run(HOOK, bad, state_dir)
        check(result.returncode == 0 and result.stdout == "", f"not fail-open for {bad!r}")
    relay_bad = run(RELAY, "{not json", state_dir)
    check(relay_bad.returncode == 0, relay_bad.stderr)
    unwritable = run(HOOK, stop_payload(), temporary_path / "file-not-dir" / "x")
    check(unwritable.returncode == 0, unwritable.stderr)

    log_text = (state_dir / "context-hook.log").read_text(encoding="utf-8")
    for action in ("trigger_wrap_up", "already_triggered", "continuation_already_active",
                   "state_reset", "context_unavailable", "below_threshold",
                   "invalid_json", "invalid_payload_type", "missing_session_id"):
        check(f'"action": "{action}"' in log_text, f"missing log action {action}")
    check("this is not JSON" not in log_text, "log leaked raw input")
    check('"tool": "claude"' in log_text, "log entries must name the tool")
    check("last_assistant_message" not in log_text, "log leaked message text")
    check("SECRET-PROMPT-TEXT" not in log_text, "log leaked the prompt")


def test_prune(temporary_path: Path) -> None:
    state_dir = temporary_path / "prune-state"
    state_dir.mkdir()
    old_snapshot = state_dir / "claude-context-old-session.json"
    old_state = state_dir / "claude-old-session.json"
    upstream = state_dir / "claude-statusline-upstream.json"
    for path in (old_snapshot, old_state, upstream):
        path.write_text("{}", encoding="utf-8")
        ancient = 1_600_000_000  # 2020
        os.utime(path, (ancient, ancient))
    fresh = state_dir / "claude-context-fresh.json"
    fresh.write_text("{}", encoding="utf-8")

    started = run(HOOK, session_start("startup"), state_dir)
    check(started.returncode == 0 and started.stdout == "", started.stdout)
    check(not old_snapshot.exists() and not old_state.exists(), "old files not pruned")
    check(upstream.exists(), "upstream statusLine must never be pruned")
    check(fresh.exists(), "fresh snapshot must survive")


def test_transcript_augmentation(temporary_path: Path) -> None:
    """The transcript tail closes the one-turn lag of the status line snapshot."""

    state_dir = temporary_path / "transcript-state"
    full = temporary_path / "transcript-full.jsonl"
    full.write_text(TRANSCRIPT, encoding="utf-8")
    # Same records, cut just before the compact_boundary: what the file looks
    # like when Stop fires after an ordinary turn.
    before_compact = temporary_path / "transcript-before-compact.jsonl"
    lines = TRANSCRIPT.splitlines()
    cut = next(i for i, line in enumerate(lines) if '"compact_boundary"' in line)
    before_compact.write_text("\n".join(lines[:cut]) + "\n", encoding="utf-8")

    # Snapshot says 0 tokens (fresh session shape); transcript says 41,867 of 1M.
    run(RELAY, STATUS_FRESH, state_dir)
    stale_snapshot = run(HOOK, stop_payload(transcript_path=str(before_compact)), state_dir,
                         WRAP_UP_CONTEXT_THRESHOLD="4")
    check('"decision": "block"' in stale_snapshot.stdout, stale_snapshot.stdout)
    check("41,867/1,000,000" in stale_snapshot.stdout, stale_snapshot.stdout)

    # After a compact the pre-compact usage must not count.
    run(HOOK, session_start("compact"), state_dir)
    run(RELAY, STATUS_FRESH, state_dir)
    post_compact = run(HOOK, stop_payload(transcript_path=str(full)), state_dir,
                       WRAP_UP_CONTEXT_THRESHOLD="1")
    check(post_compact.returncode == 0 and post_compact.stdout == "", post_compact.stdout)

    # Snapshot ahead of the transcript: the larger value wins (18% > 4%).
    run(HOOK, session_start("clear"), state_dir)
    run(RELAY, STATUS_REAL, state_dir)
    ahead = run(HOOK, stop_payload(transcript_path=str(before_compact)), state_dir,
                WRAP_UP_CONTEXT_THRESHOLD="10")
    check("179,882/1,000,000" in ahead.stdout, ahead.stdout)

    # Missing / unreadable transcript never blocks the snapshot path.
    run(HOOK, session_start("clear"), state_dir)
    run(RELAY, STATUS_REAL, state_dir)
    missing = run(HOOK, stop_payload(transcript_path=str(temporary_path / "nope.jsonl")),
                  state_dir, WRAP_UP_CONTEXT_THRESHOLD="10")
    check('"decision": "block"' in missing.stdout, missing.stdout)
    garbage = temporary_path / "garbage.jsonl"
    garbage.write_bytes(b"\xff\xfe not json\n{\"type\": 1}\n")
    run(HOOK, session_start("clear"), state_dir)
    run(RELAY, STATUS_REAL, state_dir)
    unreadable = run(HOOK, stop_payload(transcript_path=str(garbage)), state_dir,
                     WRAP_UP_CONTEXT_THRESHOLD="10")
    check('"decision": "block"' in unreadable.stdout, unreadable.stdout)


def test_relay_upstream(temporary_path: Path) -> None:
    state_dir = temporary_path / "relay-state"
    state_dir.mkdir()
    marker = temporary_path / "upstream-saw.json"
    upstream = {"type": "command", "command": f"cat > {marker}; printf 'UPSTREAM-LINE'"}
    (state_dir / "claude-statusline-upstream.json").write_text(json.dumps(upstream))
    relayed = run(RELAY, STATUS_REAL, state_dir)
    check(relayed.returncode == 0 and relayed.stdout == "UPSTREAM-LINE", relayed.stdout)
    check(marker.read_text() == STATUS_REAL, "upstream must receive the untouched payload")

    (state_dir / "claude-statusline-upstream.json").write_text(
        json.dumps({"type": "command", "command": "exit 3"})
    )
    broken = run(RELAY, STATUS_REAL, state_dir)
    check(broken.returncode == 0, "relay must be fail-open when upstream fails")


def run_installer(config: Path, state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), "--config", str(config), "--hook", str(HOOK),
         "--relay", str(RELAY), "--state-dir", str(state_dir), *args],
        text=True, capture_output=True, check=False,
    )


def test_installer(temporary_path: Path) -> None:
    state_dir = temporary_path / "install-state"
    config = temporary_path / "settings.json"
    original = {
        "permissions": {"allow": ["Bash(git status)"], "defaultMode": "auto"},
        "model": "opus",
        "hooks": {
            "PreToolUse": [{"matcher": "Grep", "hooks": [{"type": "command", "command": "gate"}]}],
            "SessionStart": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "state.sh session"}]},
                {"matcher": "compact", "hooks": [{"type": "command", "command": "reminder"}]},
            ],
        },
        "statusLine": {"type": "command", "command": "bash ~/.claude/statusline.sh",
                       "refreshInterval": 30},
    }
    config.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    os.chmod(config, 0o640)

    installed = run_installer(config, state_dir)
    check(installed.returncode == 0, installed.stderr)
    check("backup:" in installed.stdout, installed.stdout)
    backups = list(temporary_path.glob("settings.json.bak-wrap-up-*"))
    check(len(backups) == 1 and json.loads(backups[0].read_text()) == original, "backup differs")
    check(os.stat(config).st_mode & 0o777 == 0o640, "file mode not preserved")

    updated = json.loads(config.read_text(encoding="utf-8"))
    # Everything that was there before is still there, byte for byte.
    for key in ("permissions", "model"):
        check(updated[key] == original[key], f"{key} changed")
    check(updated["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"], "PreToolUse changed")
    check(updated["hooks"]["SessionStart"][:2] == original["hooks"]["SessionStart"],
          "existing SessionStart groups changed")
    for event in ("Stop", "UserPromptSubmit"):
        commands = [h["command"] for g in updated["hooks"][event] for h in g["hooks"]]
        check(commands == [str(HOOK.resolve())], f"{event}: {commands}")
        check("matcher" not in updated["hooks"][event][0], f"{event} group must have no matcher")
    added = updated["hooks"]["SessionStart"][2]
    check(added["matcher"] == "startup|clear|compact", str(added))
    check(added["hooks"][0]["command"] == str(HOOK.resolve()), str(added))
    check(updated["statusLine"]["command"] == str(RELAY.resolve()), str(updated["statusLine"]))
    check(updated["statusLine"]["refreshInterval"] == 30, "refreshInterval dropped")
    saved = json.loads((state_dir / "claude-statusline-upstream.json").read_text())
    check(saved == original["statusLine"], "upstream statusLine not saved verbatim")

    # Idempotent: a second run changes nothing and makes no new backup.
    again = run_installer(config, state_dir)
    check(again.returncode == 0 and again.stdout.startswith("already configured:"), again.stdout)
    check(json.loads(config.read_text()) == updated, "second run modified settings")
    check(len(list(temporary_path.glob("settings.json.bak-wrap-up-*"))) == 1, "extra backup")
    check(saved == json.loads((state_dir / "claude-statusline-upstream.json").read_text()),
          "second run must not overwrite the saved upstream with the relay itself")

    # Uninstall restores the original document exactly.
    removed = run_installer(config, state_dir, "--uninstall")
    check(removed.returncode == 0 and removed.stdout.startswith("updated:"), removed.stdout)
    check(json.loads(config.read_text()) == original, "uninstall did not restore original")

    # Fresh install into a missing settings.json.
    fresh = temporary_path / "fresh" / "settings.json"
    created = run_installer(fresh, state_dir / "fresh")
    check(created.returncode == 0, created.stderr)
    fresh_config = json.loads(fresh.read_text())
    check(fresh_config["statusLine"] == {"type": "command", "command": str(RELAY.resolve())},
          str(fresh_config["statusLine"]))
    check(not (state_dir / "fresh" / "claude-statusline-upstream.json").exists(),
          "no upstream file should be written when there was no statusLine")

    # Malformed settings.json is refused without being touched.
    bad = temporary_path / "bad.json"
    bad.write_text("{ nope", encoding="utf-8")
    refused = run_installer(bad, state_dir)
    check(refused.returncode != 0 and bad.read_text() == "{ nope", "malformed settings modified")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="wrap-up-claude-hook-test-") as temporary:
        temporary_path = Path(temporary)
        for test in (test_relay_and_hook, test_transcript_augmentation, test_prune,
                     test_relay_upstream, test_installer):
            test(temporary_path)
            print(f"PASS: {test.__name__}")
    print("claude context hook self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
