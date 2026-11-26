#!/usr/bin/env python3
"""Executable regression tests for the Codex context wrap-up hook."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hooks" / "codex-context-wrap-up.py"
INSTALLER = ROOT / "hooks" / "install_codex_hook.py"
FIXTURE = ROOT / "tests" / "fixtures" / "codex-token-count.jsonl"


def run_hook(payload: object, state_dir: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["WRAP_UP_STATE_DIR"] = str(state_dir)
    input_text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=input_text,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def payload(transcript_path: Path, event: str = "Stop", **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "session_id": "session-test-70",
        "transcript_path": str(transcript_path),
        "cwd": str(ROOT),
        "hook_event_name": event,
    }
    value.update(extra)
    return value


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="wrap-up-hook-test-") as temporary:
        temporary_path = Path(temporary)
        transcript = temporary_path / "rollout.jsonl"
        shutil.copyfile(FIXTURE, transcript)
        state_dir = temporary_path / "state"

        first = run_hook(payload(transcript), state_dir)
        assert first.returncode == 0, first.stderr
        assert '"decision": "block"' in first.stdout, first.stdout
        assert "$wrap-up" in first.stdout, first.stdout

        duplicate = run_hook(payload(transcript), state_dir)
        assert duplicate.returncode == 0, duplicate.stderr
        assert duplicate.stdout == "", duplicate.stdout

        reset = run_hook(
            payload(transcript, event="SessionStart", source="compact"),
            state_dir,
        )
        assert reset.returncode == 0, reset.stderr
        assert reset.stdout == "", reset.stdout

        after_reset = run_hook(payload(transcript), state_dir)
        assert after_reset.returncode == 0, after_reset.stderr
        assert '"decision": "block"' in after_reset.stdout, after_reset.stdout

        malformed = run_hook("this is not JSON", state_dir)
        assert malformed.returncode == 0, malformed.stderr
        assert malformed.stdout == "", malformed.stdout

        missing_transcript = run_hook(
            payload(temporary_path / "missing.jsonl", session_id="missing-transcript"),
            state_dir,
        )
        assert missing_transcript.returncode == 0, missing_transcript.stderr
        assert missing_transcript.stdout == "", missing_transcript.stdout

        log_path = state_dir / "context-hook.log"
        log_text = log_path.read_text(encoding="utf-8")
        assert '"action": "trigger_wrap_up"' in log_text
        assert '"action": "state_reset"' in log_text
        assert '"action": "invalid_json"' in log_text
        assert "this is not JSON" not in log_text

        config = temporary_path / "hooks.json"
        config.write_text('{"hooks": {"SessionStart": []}}\n', encoding="utf-8")
        install_environment = os.environ.copy()
        install_environment["CODEX_HOME"] = str(temporary_path)
        installed = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--config",
                str(config),
                "--hook",
                str(SCRIPT),
            ],
            text=True,
            capture_output=True,
            env=install_environment,
            check=False,
        )
        assert installed.returncode == 0, installed.stderr
        installed_config = json.loads(config.read_text(encoding="utf-8"))
        assert any(
            item.get("command") == str(SCRIPT.resolve())
            for group in installed_config["hooks"]["Stop"]
            for item in group["hooks"]
        )
        assert any(
            group.get("matcher") == "^compact$"
            for group in installed_config["hooks"]["SessionStart"]
        )

        installed_again = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--config",
                str(config),
                "--hook",
                str(SCRIPT),
            ],
            text=True,
            capture_output=True,
            env=install_environment,
            check=False,
        )
        assert installed_again.returncode == 0, installed_again.stderr
        assert installed_again.stdout.startswith("already configured:"), installed_again.stdout

    print("context hook self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
