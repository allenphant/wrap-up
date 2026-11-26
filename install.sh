#!/usr/bin/env bash
# 把 wrap-up skill 安裝到 Claude Code 與 Codex。
# Install the wrap-up skill into Claude Code and Codex.
#
# 用 symlink 指向 repo 內的目錄，讓兩個工具共用同一份檔案，git pull 之後同時更新。
# 這裡的 symlink 是安全的 —— skill 目錄是唯讀的。README 裡警告的 symlink 問題
# 只適用於專案中會被寫入的 CLAUDE.md / AGENTS.md 指標檔。
set -euo pipefail

LANG_DIR="zh-TW"
INSTALL_CODEX_HOOK=0
INSTALL_CLAUDE_HOOK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_DIR="${2:-}"; shift 2 ;;
    --lang=*) LANG_DIR="${1#*=}"; shift ;;
    --hooks) INSTALL_CODEX_HOOK=1; INSTALL_CLAUDE_HOOK=1; shift ;;
    --codex-hook) INSTALL_CODEX_HOOK=1; shift ;;
    --claude-hook) INSTALL_CLAUDE_HOOK=1; shift ;;
    -h|--help) echo "usage: $0 [--lang zh-TW|en] [--hooks | --codex-hook | --claude-hook]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SRC="$REPO/skills/$LANG_DIR/wrap-up"
[ -f "$SRC/SKILL.md" ] || { echo "找不到 $SRC/SKILL.md（--lang 只接受 zh-TW 或 en）" >&2; exit 1; }

installed=0
for target in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  tool=$(basename "$(dirname "$target")")
  if [ ! -d "$(dirname "$target")" ]; then
    echo "skip: $tool 未安裝（$(dirname "$target") 不存在）"
    continue
  fi
  mkdir -p "$target"
  dest="$target/wrap-up"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    # 備份必須放在 skills/ 之外，否則會被當成另一個 skill 載入。
    # Back up outside skills/, or the backup gets loaded as a second skill.
    backup_dir="$(dirname "$target")/skill-backups"
    mkdir -p "$backup_dir"
    backup="$backup_dir/wrap-up.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$dest" "$backup"
    echo "existing → $backup"
  fi
  ln -s "$SRC" "$dest"
  echo "installed: $dest -> $SRC"
  installed=$((installed + 1))
done

[ "$installed" -gt 0 ] || { echo "沒有偵測到 Claude Code 或 Codex 的 skills 目錄。" >&2; exit 1; }

if [ "$INSTALL_CODEX_HOOK" -eq 1 ] && [ -d "${CODEX_HOME:-$HOME/.codex}" ]; then
  python3 "$REPO/hooks/install_codex_hook.py" \
    --hook "$REPO/hooks/codex-context-wrap-up.py"
fi

# Claude Code 的 hook 輸入沒有 context 用量，所以同時把 statusLine 包一層 relay
# 來記錄官方的 context_window 數字。原本的 statusLine 指令會被保留並繼續執行。
# Claude Code hook input has no context usage, so the statusLine is wrapped by a
# relay that records the official context_window numbers. The previous statusLine
# command is kept and still runs.
if [ "$INSTALL_CLAUDE_HOOK" -eq 1 ] && [ -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ]; then
  python3 "$REPO/hooks/install_claude_hook.py" \
    --hook "$REPO/hooks/claude-context-wrap-up.py" \
    --relay "$REPO/hooks/claude-statusline-relay.py"
fi

echo
echo "完成。在 Claude Code 或 Codex 輸入 /wrap-up 即可使用。"
echo "Done. Type /wrap-up in Claude Code or Codex."
if [ "$INSTALL_CODEX_HOOK" -eq 1 ]; then
  echo "Codex context hook: 70% threshold, reset after compact."
  echo "Review and trust it once with /hooks in Codex."
fi
if [ "$INSTALL_CLAUDE_HOOK" -eq 1 ]; then
  echo "Claude Code context hook: 70% threshold, reset after compact."
  echo "Running Claude Code sessions pick up the new hooks and statusLine on their own (verified on 2.1.278); otherwise restart or use /hooks."
fi
