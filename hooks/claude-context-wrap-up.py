#!/usr/bin/env python3
"""Trigger the wrap-up skill before a Claude Code context window gets crowded.

Claude Code's hook input carries no context-usage field (hook schema verified
on 2.1.278: the common fields are session_id, transcript_path, cwd, prompt_id,
permission_mode, agent_id, agent_type and effort), and the transcript never
records the context window size.

So this hook reads the per-session snapshot that `claude-statusline-relay.py`
records from the official statusLine JSON (`context_window`: the window size
and the same (input + cache_creation + cache_read) sum Claude Code shows as
used_percentage). Measured on 2.1.278, both that snapshot (refreshed 10-50 s
after Stop) and the transcript (flushed after the Stop hooks finish) still
describe the previous turn when Stop fires. So the hook listens on two events:

- Stop: answers decision:block, exactly like the Codex hook, when the last
  known usage is already over the threshold.
- UserPromptSubmit: by then both sources are fresh; if the previous turn pushed
  usage over the threshold, additionalContext asks Claude to run wrap-up
  before the new request. This closes the one-turn lag of Stop.

Whichever event notices first wins; the shared per-session state file makes
sure the other one stays quiet. For the token count the hook takes the larger
of the snapshot's total_input_tokens and the transcript's latest main-thread
assistant usage (same formula), against the snapshot's window size; records
after a compact_boundary are ignored so pre-compact usage never leaks into the
next window.

Semantics match the Codex hook: default threshold 70%, at most one trigger per
context window, reset on SessionStart for startup / clear / compact, and
deliberately fail-open (bad JSON, missing fields, missing files and any
exception all exit 0).
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_THRESHOLD = 70.0
TAIL_BYTES = 16 * 1024 * 1024
SAFE_SESSION_ID = re.compile(r"[^A-Za-z0-9_.-]+")
RESET_SOURCES = {"startup", "clear", "compact"}
PRUNE_AFTER_SECONDS = 30 * 24 * 3600


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _threshold() -> float:
    configured = _number(os.environ.get("WRAP_UP_CONTEXT_THRESHOLD"))
    if configured is None or configured <= 0 or configured > 100:
        return DEFAULT_THRESHOLD
    return configured


def _state_dir() -> Path | None:
    configured = os.environ.get("WRAP_UP_STATE_DIR")
    if configured:
        return Path(configured).expanduser()

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "wrap-up"

    home = os.environ.get("HOME")
    if home:
        return Path(home) / ".local" / "state" / "wrap-up"
    return None


def _safe_session_id(session_id: str) -> str:
    value = SAFE_SESSION_ID.sub("_", session_id).strip("._")
    return (value or "unknown")[:160]


def _mkdir_state_dir() -> Path | None:
    directory = _state_dir()
    if directory is None:
        return None
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        return directory
    except OSError:
        return None


def _log_path() -> Path | None:
    directory = _mkdir_state_dir()
    return directory / "context-hook.log" if directory else None


def _log(payload: dict[str, Any], action: str, **details: Any) -> None:
    """Write an unconditional, metadata-only diagnostic entry.

    Logging failures are swallowed because diagnostics must never change hook
    behavior. Prompt text, last_assistant_message and transcript contents are
    intentionally excluded.
    """

    record: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "claude",
        "event": payload.get("hook_event_name"),
        "session": str(payload.get("session_id") or "")[-12:],
        "action": action,
    }
    record.update(details)
    try:
        path = _log_path()
        if path is None:
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(path, 0o600)
    except Exception:
        return


def _state_path(session_id: str) -> Path | None:
    directory = _mkdir_state_dir()
    return directory / f"claude-{_safe_session_id(session_id)}.json" if directory else None


def _snapshot_path(session_id: str) -> Path | None:
    directory = _state_dir()
    return directory / f"claude-context-{_safe_session_id(session_id)}.json" if directory else None


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(session_id: str, state: dict[str, Any]) -> bool:
    path = _state_path(session_id)
    if path is None:
        return False
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        return True
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _json_lines_from_tail(path: Path) -> Iterator[dict[str, Any]]:
    """Newest-first JSON records from the last TAIL_BYTES of a .jsonl file.

    Lazy on purpose: the caller usually stops at the first assistant record,
    and this runs on every prompt submit and every Stop.
    """

    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES), os.SEEK_SET)
            data = handle.read()
    except OSError:
        return

    for raw_line in reversed(data.splitlines()):
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            continue
        if isinstance(value, dict):
            yield value


def _transcript_used_tokens(transcript_path: Any) -> int | None:
    """Latest main-thread assistant usage in the transcript, or None.

    Mirrors Claude Code's own formula (input + cache_creation + cache_read).
    Stops at a compact_boundary system record: everything before it belongs to
    the previous context window.
    """

    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.is_file():
        return None

    for record in _json_lines_from_tail(path):
        record_type = record.get("type")
        if record_type == "system" and record.get("subtype") == "compact_boundary":
            return None
        if record_type != "assistant" or record.get("isSidechain") is True:
            continue
        message = record.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        input_tokens = _number(usage.get("input_tokens"))
        if input_tokens is None:
            continue
        total = input_tokens
        for key in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            total += _number(usage.get(key)) or 0.0
        return int(total)
    return None


def _context_usage(payload: dict[str, Any], session_id: str) -> tuple[float, int | None, int | None] | None:
    """Return (used_percent, used_tokens, window_tokens) for this session.

    The relay snapshot must belong to this session and supplies the window
    size. The token count is the larger of the snapshot's total_input_tokens
    and the transcript's latest assistant usage, because the snapshot lags Stop
    by one turn. used_percentage is the fallback when no token counts exist.
    """

    snapshot = _read_json(_snapshot_path(session_id))
    if snapshot.get("session_id") != session_id:
        return None
    context_window = snapshot.get("context_window")
    if not isinstance(context_window, dict):
        return None

    used_tokens = _number(context_window.get("total_input_tokens"))
    window_tokens = _number(context_window.get("context_window_size"))
    if window_tokens is not None and window_tokens > 0:
        transcript_tokens = _transcript_used_tokens(payload.get("transcript_path"))
        candidates = [value for value in (used_tokens, transcript_tokens) if value is not None]
        if candidates:
            best = max(candidates)
            return best / window_tokens * 100.0, int(best), int(window_tokens)

    used_percent = _number(context_window.get("used_percentage"))
    if used_percent is None:
        return None
    return used_percent, None, None


def _prune_old_files() -> None:
    """Drop per-session files nobody will read again (one file per session)."""

    directory = _state_dir()
    if directory is None:
        return
    cutoff = datetime.now(timezone.utc).timestamp() - PRUNE_AFTER_SECONDS
    try:
        for path in directory.glob("claude-*.json"):
            if path.name == "claude-statusline-upstream.json":
                continue
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        return


def _handle_session_start(payload: dict[str, Any]) -> int:
    source = payload.get("source")
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id and source in RESET_SOURCES:
        _unlink(_state_path(session_id))
        # The pre-compact snapshot is still on disk until the status line
        # refreshes; dropping it prevents an immediate re-trigger.
        _unlink(_snapshot_path(session_id))
        if source == "startup":
            _prune_old_files()
        _log(payload, "state_reset", source=source)
    else:
        _log(payload, "session_start_ignored", source=source)
    return 0


def _handle_threshold_event(payload: dict[str, Any]) -> int:
    """Shared body of Stop and UserPromptSubmit; the output shape differs."""

    event = payload.get("hook_event_name")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        _log(payload, "missing_session_id")
        return 0

    if event == "Stop" and payload.get("stop_hook_active") is True:
        _log(payload, "continuation_already_active")
        return 0

    usage = _context_usage(payload, session_id)
    if usage is None:
        _log(payload, "context_unavailable")
        return 0

    used_percent, used_tokens, window_tokens = usage
    threshold = _threshold()
    state = _read_json(_state_path(session_id))
    if state.get("triggered") is True:
        _log(
            payload,
            "already_triggered",
            used_percent=round(used_percent, 2),
            threshold=threshold,
        )
        return 0

    if used_percent < threshold:
        _log(
            payload,
            "below_threshold",
            used_percent=round(used_percent, 2),
            threshold=threshold,
        )
        return 0

    state = {
        "triggered": True,
        "used_percent": round(used_percent, 2),
        "used_tokens": used_tokens,
        "context_window_size": window_tokens,
        "threshold": threshold,
    }
    if not _write_state(session_id, state):
        _log(
            payload,
            "state_write_failed",
            used_percent=round(used_percent, 2),
            threshold=threshold,
        )
        return 0

    _log(
        payload,
        "trigger_wrap_up",
        used_percent=round(used_percent, 2),
        threshold=threshold,
        used_tokens=used_tokens,
        context_window_size=window_tokens,
    )
    if used_tokens is not None and window_tokens is not None:
        detail = f"({used_tokens:,}/{window_tokens:,} tokens)"
    else:
        detail = "(from the status line)"
    if event == "UserPromptSubmit":
        context = (
            f"Context window reached {used_percent:.1f}% {detail}. "
            "Before working on this prompt, run the wrap-up skill (/wrap-up) "
            "to save the current project state, then continue with the request."
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        }
    else:
        reason = (
            f"Context window reached {used_percent:.1f}% {detail}. "
            "Run the wrap-up skill (/wrap-up) now to save the current project "
            "state before continuing."
        )
        output = {"decision": "block", "reason": reason}
    print(json.dumps(output, ensure_ascii=False))
    return 0


def main() -> int:
    raw_input = sys.stdin.read()
    try:
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except (ValueError, TypeError):
        payload = {}
        _log(payload, "invalid_json")
        return 0

    if not isinstance(payload, dict):
        _log({}, "invalid_payload_type")
        return 0

    event = payload.get("hook_event_name")
    try:
        if event == "SessionStart":
            return _handle_session_start(payload)
        if event in ("Stop", "UserPromptSubmit"):
            return _handle_threshold_event(payload)
        _log(payload, "ignored_event")
        return 0
    except Exception as error:  # pragma: no cover - final fail-open guard
        _log(payload, "unexpected_error", error=type(error).__name__)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
