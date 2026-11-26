#!/usr/bin/env python3
"""Mirror Claude Code's statusLine JSON into a per-session context snapshot.

Claude Code hook input (verified on 2.1.278 against the binary's hook schema
and a real capture) carries no context-usage field, and the transcript is not
yet updated when the Stop hook fires. The only official structured source of
the context percentage is the JSON that Claude Code pipes into the
`statusLine.command`. This relay sits in front of the user's existing
statusLine command, records `context_window` for the current session, then
forwards the untouched payload to the previous command so the status line
keeps rendering exactly as before.

Everything here is fail-open: any error results in the upstream command still
running (or a minimal fallback line) and exit code 0. The relay never logs per
refresh because it runs every few seconds; only failures are logged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UPSTREAM_TIMEOUT_SECONDS = 10
SAFE_SESSION_ID = re.compile(r"[^A-Za-z0-9_.-]+")


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


def _safe_session_id(session_id: str) -> str:
    value = SAFE_SESSION_ID.sub("_", session_id).strip("._")
    return (value or "unknown")[:160]


def snapshot_path(directory: Path, session_id: str) -> Path:
    return directory / f"claude-context-{_safe_session_id(session_id)}.json"


def upstream_path(directory: Path) -> Path:
    return directory / "claude-statusline-upstream.json"


def _log_failure(action: str, **details: Any) -> None:
    try:
        directory = _mkdir_state_dir()
        if directory is None:
            return
        record = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": "claude",
            "event": "statusLine",
            "action": action,
        }
        record.update(details)
        path = directory / "context-hook.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(path, 0o600)
    except Exception:
        return


def _atomic_write_json(path: Path, value: dict[str, Any]) -> bool:
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
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
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


def record_snapshot(payload: dict[str, Any]) -> None:
    """Persist metadata only: session id, version, model id and context_window."""

    session_id = payload.get("session_id")
    context_window = payload.get("context_window")
    if not isinstance(session_id, str) or not session_id:
        return
    if not isinstance(context_window, dict):
        return
    directory = _mkdir_state_dir()
    if directory is None:
        return

    model = payload.get("model")
    snapshot = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "version": payload.get("version"),
        "model_id": model.get("id") if isinstance(model, dict) else None,
        "context_window": {
            key: context_window.get(key)
            for key in (
                "total_input_tokens",
                "context_window_size",
                "used_percentage",
                "remaining_percentage",
            )
        },
    }
    if not _atomic_write_json(snapshot_path(directory, session_id), snapshot):
        _log_failure("snapshot_write_failed", session=session_id[-12:])


def _upstream_command() -> str | None:
    directory = _state_dir()
    if directory is None:
        return None
    try:
        value = json.loads(upstream_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    command = value.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    return command


def _fallback_line(payload: dict[str, Any]) -> str:
    model = payload.get("model")
    name = model.get("display_name") if isinstance(model, dict) else None
    context_window = payload.get("context_window")
    used = context_window.get("used_percentage") if isinstance(context_window, dict) else None
    line = f"[{name}]" if isinstance(name, str) and name else "[Claude]"
    if isinstance(used, (int, float)) and not isinstance(used, bool):
        line += f" · ctx {int(used)}%"
    return line


def forward(raw_input: bytes, payload: dict[str, Any]) -> None:
    command = _upstream_command()
    if command is None:
        sys.stdout.write(_fallback_line(payload))
        sys.stdout.flush()
        return
    try:
        completed = subprocess.run(
            ["bash", "-c", command],
            input=raw_input,
            capture_output=True,
            timeout=UPSTREAM_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _log_failure("upstream_failed", error=type(error).__name__)
        sys.stdout.write(_fallback_line(payload))
        sys.stdout.flush()
        return
    sys.stdout.buffer.write(completed.stdout)
    sys.stdout.flush()


def main() -> int:
    raw_input = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw_input.decode("utf-8")) if raw_input.strip() else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        record_snapshot(payload)
    except Exception as error:  # pragma: no cover - final fail-open guard
        _log_failure("unexpected_error", error=type(error).__name__)

    try:
        forward(raw_input, payload)
    except Exception as error:  # pragma: no cover - final fail-open guard
        _log_failure("forward_unexpected_error", error=type(error).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
