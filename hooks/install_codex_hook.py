#!/usr/bin/env python3
"""Install the context hook into a Codex hooks.json file."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def add_group(
    groups: list[Any],
    matcher: str | None,
    handler: dict[str, Any],
) -> bool:
    command = handler.get("command")
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_matcher = group.get("matcher")
        if matcher is None:
            if group_matcher not in (None, ""):
                continue
        elif group_matcher != matcher:
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        if any(isinstance(item, dict) and item.get("command") == command for item in handlers):
            return False

    group: dict[str, Any] = {"hooks": [handler]}
    if matcher is not None:
        group["matcher"] = matcher
    groups.append(group)
    return True


def install(config_path: Path, hook_path: Path) -> tuple[bool, Path | None]:
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit(f"無法讀取 Codex hooks 設定：{config_path}: {error}") from error
        if not isinstance(config, dict):
            raise SystemExit(f"Codex hooks 設定不是 JSON object：{config_path}")
        original_mode = config_path.stat().st_mode & 0o777
    else:
        config = {}
        original_mode = 0o600

    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"Codex hooks 欄位不是 JSON object：{config_path}")

    stop_groups = hooks.setdefault("Stop", [])
    session_start_groups = hooks.setdefault("SessionStart", [])
    if not isinstance(stop_groups, list) or not isinstance(session_start_groups, list):
        raise SystemExit(f"Codex hook event 欄位不是 JSON array：{config_path}")

    hook_command = str(hook_path.resolve())
    common_handler = {
        "type": "command",
        "command": hook_command,
        "timeout": 5,
        "statusMessage": "Checking context for wrap-up",
    }
    changed = add_group(stop_groups, None, dict(common_handler))
    changed = add_group(
        session_start_groups,
        "^compact$",
        dict(common_handler),
    ) or changed
    if not changed:
        return False, None

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
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, config_path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise SystemExit(f"無法寫入 Codex hooks 設定：{config_path}: {error}") from error

    return True, backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Codex hooks.json path; defaults to $CODEX_HOME/hooks.json or ~/.codex/hooks.json",
    )
    args = parser.parse_args()

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config_path = (args.config or (codex_home / "hooks.json")).expanduser()
    hook_path = args.hook.expanduser().resolve()
    if not hook_path.is_file():
        raise SystemExit(f"找不到 hook：{hook_path}")

    changed, backup_path = install(config_path, hook_path)
    if not changed:
        print(f"already configured: {config_path}")
        return 0
    print(f"updated: {config_path}")
    if backup_path is not None:
        print(f"backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
