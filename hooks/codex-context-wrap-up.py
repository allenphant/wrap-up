#!/usr/bin/env python3
"""Trigger the wrap-up skill before a Codex context window gets crowded.

Codex does not include context usage in command-hook input. Its transcript does
include token_count events, so the hook reads the latest event from the tail of
that transcript and calculates input_tokens / model_context_window.

This hook is deliberately fail-open. It must never block a turn because a
transcript is missing, malformed, or written in a future format.
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
from typing import Any


DEFAULT_THRESHOLD = 70.0
TAIL_BYTES = 16 * 1024 * 1024
SAFE_SESSION_ID = re.compile(r"[^A-Za-z0-9_.-]+")


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
    behavior. Prompt text and transcript contents are intentionally excluded.
    """

    record: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
    return directory / f"codex-{_safe_session_id(session_id)}.json" if directory else None


def _read_state(session_id: str) -> dict[str, Any]:
    path = _state_path(session_id)
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


def _clear_state(session_id: str) -> None:
    path = _state_path(session_id)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _json_lines_from_tail(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES), os.SEEK_SET)
            data = handle.read()
    except OSError:
        return []

    records: list[dict[str, Any]] = []
    for raw_line in reversed(data.splitlines()):
        try:
            value = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _latest_context_usage(transcript_path: Any) -> tuple[float, float, float] | None:
    if not isinstance(transcript_path, str) or not transcript_path:
        return None

    path = Path(transcript_path)
    if not path.is_file():
        return None

    for record in _json_lines_from_tail(path):
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        last_usage = info.get("last_token_usage")
        if not isinstance(last_usage, dict):
            continue
        used_tokens = _number(last_usage.get("input_tokens"))
        window_tokens = _number(info.get("model_context_window"))
        if used_tokens is None or window_tokens is None or window_tokens <= 0:
            continue
        return used_tokens / window_tokens * 100.0, used_tokens, window_tokens
    return None


def _handle_session_start(payload: dict[str, Any]) -> int:
    source = payload.get("source")
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and source in {"startup", "clear", "compact"}:
        _clear_state(session_id)
        _log(payload, "state_reset", source=source)
    else:
        _log(payload, "session_start_ignored", source=source)
    return 0


def _handle_stop(payload: dict[str, Any]) -> int:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        _log(payload, "missing_session_id")
        return 0

    if payload.get("stop_hook_active") is True:
        _log(payload, "continuation_already_active")
        return 0

    usage = _latest_context_usage(payload.get("transcript_path"))
    if usage is None:
        _log(payload, "context_unavailable")
        return 0

    used_percent, used_tokens, window_tokens = usage
    threshold = _threshold()
    state = _read_state(session_id)
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
        "used_tokens": int(used_tokens),
        "model_context_window": int(window_tokens),
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
        used_tokens=int(used_tokens),
        model_context_window=int(window_tokens),
    )
    reason = (
        f"Context window reached {used_percent:.1f}% "
        f"({int(used_tokens):,}/{int(window_tokens):,} input tokens). "
        "Run $wrap-up now to save the current project state before continuing."
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
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
        if event == "Stop":
            return _handle_stop(payload)
        _log(payload, "ignored_event")
        return 0
    except Exception as error:  # pragma: no cover - final fail-open guard
        _log(payload, "unexpected_error", error=type(error).__name__)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
