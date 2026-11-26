#!/usr/bin/env python3
"""Install the context hook and statusLine relay into Claude Code settings.json.

Two edits are made in one atomic write of ~/.claude/settings.json:

1. `hooks.Stop`, `hooks.UserPromptSubmit` and `hooks.SessionStart` (matcher
   `startup|clear|compact`) get a command entry pointing at
   claude-context-wrap-up.py. Existing hook groups are left untouched; a group
   is only appended when the command is absent.
2. `statusLine.command` is replaced by claude-statusline-relay.py. The previous
   statusLine object is saved to `<state dir>/claude-statusline-upstream.json`
   so the relay can keep rendering it, and `--uninstall` can restore it.

The file is backed up before writing, written via temp file + rename, and its
mode is preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_codex_hook import add_group  # noqa: E402

SESSION_START_MATCHER = "startup|clear|compact"
UPSTREAM_FILE = "claude-statusline-upstream.json"


def state_dir() -> Path:
    configured = os.environ.get("WRAP_UP_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home) / "wrap-up"
    return Path.home() / ".local" / "state" / "wrap-up"


def _load(config_path: Path) -> tuple[dict[str, Any], int]:
    if not config_path.exists():
        return {}, 0o600
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"無法讀取 Claude 設定：{config_path}: {error}") from error
    if not isinstance(config, dict):
        raise SystemExit(f"Claude 設定不是 JSON object：{config_path}")
    return config, config_path.stat().st_mode & 0o777


def _write(config_path: Path, config: dict[str, Any], mode: int) -> Path | None:
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_path: Path | None = None
    if config_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.bak-wrap-up-{stamp}")
        shutil.copy2(config_path, backup_path)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, config_path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise SystemExit(f"無法寫入 Claude 設定：{config_path}: {error}") from error
    return backup_path


HOOK_EVENTS = ("Stop", "UserPromptSubmit", "SessionStart")


def _hook_groups(config: dict[str, Any], config_path: Path) -> dict[str, list[Any]]:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"Claude hooks 欄位不是 JSON object：{config_path}")
    groups: dict[str, list[Any]] = {}
    for event in HOOK_EVENTS:
        groups[event] = hooks.setdefault(event, [])
        if not isinstance(groups[event], list):
            raise SystemExit(f"Claude hook event 欄位不是 JSON array：{config_path}")
    return groups


def _save_upstream(directory: Path, status_line: dict[str, Any]) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / UPSTREAM_FILE
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{UPSTREAM_FILE}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(status_line, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise SystemExit(f"無法寫入 statusLine 備份：{path}: {error}") from error
    return path


def _wrap_status_line(
    config: dict[str, Any], relay_command: str, directory: Path
) -> bool:
    current = config.get("statusLine")
    if isinstance(current, dict) and current.get("command") == relay_command:
        return False
    if isinstance(current, dict) and current.get("type", "command") == "command":
        if isinstance(current.get("command"), str) and current["command"].strip():
            _save_upstream(directory, current)
        wrapped = dict(current)
    else:
        wrapped = {}
    wrapped["type"] = "command"
    wrapped["command"] = relay_command
    config["statusLine"] = wrapped
    return True


def install(
    config_path: Path, hook_path: Path, relay_path: Path, directory: Path
) -> tuple[bool, Path | None]:
    config, mode = _load(config_path)
    groups = _hook_groups(config, config_path)

    handler = {
        "type": "command",
        "command": str(hook_path.resolve()),
        "timeout": 5,
        "statusMessage": "Checking context for wrap-up",
    }
    changed = add_group(groups["Stop"], None, dict(handler))
    changed = add_group(groups["UserPromptSubmit"], None, dict(handler)) or changed
    changed = add_group(groups["SessionStart"], SESSION_START_MATCHER, dict(handler)) or changed
    changed = _wrap_status_line(config, str(relay_path.resolve()), directory) or changed
    if not changed:
        return False, None
    return True, _write(config_path, config, mode)


def _remove_command(groups: list[Any], command: str) -> bool:
    changed = False
    for group in list(groups):
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        kept = [
            item
            for item in group["hooks"]
            if not (isinstance(item, dict) and item.get("command") == command)
        ]
        if len(kept) != len(group["hooks"]):
            changed = True
            if kept:
                group["hooks"] = kept
            else:
                groups.remove(group)
    return changed


def uninstall(
    config_path: Path, hook_path: Path, relay_path: Path, directory: Path
) -> tuple[bool, Path | None]:
    config, mode = _load(config_path)
    hooks = config.get("hooks")
    changed = False
    command = str(hook_path.resolve())
    if isinstance(hooks, dict):
        for event in HOOK_EVENTS:
            groups = hooks.get(event)
            if isinstance(groups, list):
                changed = _remove_command(groups, command) or changed
                if not groups:
                    del hooks[event]
        if not hooks:
            del config["hooks"]

    current = config.get("statusLine")
    if isinstance(current, dict) and current.get("command") == str(relay_path.resolve()):
        upstream_file = directory / UPSTREAM_FILE
        try:
            upstream = json.loads(upstream_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            upstream = None
        if isinstance(upstream, dict) and isinstance(upstream.get("command"), str):
            config["statusLine"] = upstream
        else:
            del config["statusLine"]
        changed = True

    if not changed:
        return False, None
    return True, _write(config_path, config, mode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", required=True, type=Path)
    parser.add_argument("--relay", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Claude settings.json path; defaults to $CLAUDE_CONFIG_DIR/settings.json or ~/.claude/settings.json",
    )
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    config_path = (args.config or (claude_home / "settings.json")).expanduser()
    directory = (args.state_dir or state_dir()).expanduser()
    hook_path = args.hook.expanduser().resolve()
    relay_path = args.relay.expanduser().resolve()
    if not args.uninstall:
        for path in (hook_path, relay_path):
            if not path.is_file():
                raise SystemExit(f"找不到 hook：{path}")

    action = uninstall if args.uninstall else install
    changed, backup_path = action(config_path, hook_path, relay_path, directory)
    if not changed:
        print(f"already configured: {config_path}" if not args.uninstall else f"nothing to remove: {config_path}")
        return 0
    print(f"updated: {config_path}")
    if backup_path is not None:
        print(f"backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
