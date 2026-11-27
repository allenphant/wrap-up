#!/usr/bin/env python3
"""Static regression test: both SKILL.md variants keep the in-turn approval menu
and the Before/After presentation rules.

These rules are prose for a model, so this only guards that the required
statements are still present in each language. It does not prove the model
obeys them; see tests/selftest.sh for behavioral runs.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Each requirement: (description, [substrings that must ALL appear]).
REQUIREMENTS: dict[str, list[tuple[str, list[str]]]] = {
    "skills/zh-TW/wrap-up/SKILL.md": [
        ("uses AskUserQuestion", ["AskUserQuestion"]),
        ("loads the deferred tool first", ["ToolSearch select:AskUserQuestion"]),
        ("asks within the same turn", ["同一輪對話內"]),
        ("batches when over the limit", ["最多 4 題", "最多 4 個選項", "分批"]),
        ("multiSelect with an approve-none option", ["multiSelect: true", "全部不核准", "不套用（維持原樣）"]),
        ("first question offers approve-all", ["總開關", "「全部核准」", "「依後面各題勾選」", "只涵蓋提問前已用文字印出的項目"]),
        ("switch and items share one call", ["總開關與分題放在同一次呼叫", "不得先單獨問總開關"]),
        ("unanswered counts as not approved", ["視為未核准"]),
        ("non-interactive fallback", ["非互動情境"]),
        ("Before/After in the list", ["變更前／變更後"]),
        ("Before/After in option description", ["變更前：… → 變更後：…"]),
        ("class B shows reference count", ["references in repo: N"]),
    ],
    "skills/en/wrap-up/SKILL.md": [
        ("uses AskUserQuestion", ["AskUserQuestion"]),
        ("loads the deferred tool first", ["ToolSearch select:AskUserQuestion"]),
        ("asks within the same turn", ["in this same turn"]),
        ("batches when over the limit", ["At most 4 questions", "4 options", "further rounds"]),
        ("multiSelect with an approve-none option", ["multiSelect: true", "Approve none", "Do not apply (leave as is)"]),
        ("first question offers approve-all", ["overall switch", "\"Approve all\"", "\"Use the ticks below\"", "covers only the items printed as text"]),
        ("switch and items share one call", ["in the same call", "Never ask the switch alone"]),
        ("unanswered counts as not approved", ["= not approved"]),
        ("non-interactive fallback", ["Non-interactive runs"]),
        ("Before/After in the list", ["**Before / After**"]),
        ("Before/After in option description", ["Before: … → After: …"]),
        ("class B shows reference count", ["references in repo: N"]),
    ],
}

# Phrases that would mean the old "stop and wait for the next message" flow is back.
FORBIDDEN: dict[str, list[str]] = {
    "skills/zh-TW/wrap-up/SKILL.md": ["有未核准項目時停在清單，說明本技能要求核准後才刪改，不提供下一個對話的啟動句。若全無發現", "單獨一次呼叫"],
    "skills/en/wrap-up/SKILL.md": ["stop and wait for my reply", "Run this only after I reply", "in its own call"],
}


def main() -> int:
    failures: list[str] = []
    for relative, checks in REQUIREMENTS.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"{relative}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        for description, needles in checks:
            for needle in needles:
                if needle not in text:
                    failures.append(f"{relative}: missing [{description}] -> {needle!r}")
        for needle in FORBIDDEN.get(relative, []):
            if needle in text:
                failures.append(f"{relative}: old flow reappeared -> {needle!r}")

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("skill approval menu check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
