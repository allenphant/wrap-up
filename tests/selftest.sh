#!/usr/bin/env bash
# wrap-up skill 的行為回歸測試 / behavioral regression tests.
#
# 這些防護是用散文寫給模型看的，不是程式強制的，所以每次改動 SKILL.md 都要重跑。
# These guards are prose instructions to a model, not code. Re-run after any SKILL.md change.
#
# 全程在暫存目錄操作，不碰任何真實專案。
# Everything runs in temp dirs; no real project is touched.
set -u
PASS=0; FAIL=0
uuid() { python3 -c 'import uuid;print(uuid.uuid4())'; }

run() { # $1=名稱  $2=測試函式
  local d; d=$(mktemp -d)
  if ( cd "$d" && "$2" ); then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1"; FAIL=$((FAIL+1))
    # 失敗時把模型的實際輸出印出來，否則 flaky 失敗無從診斷
    local f
    for f in "$d"/out*.log; do
      [ -f "$f" ] || continue
      echo "  ── $(basename "$f") 末段 ──"
      tail -15 "$f" | sed 's/^/  | /'
    done
  fi
  rm -rf "$d"
}

# 階段一結束時不可以出現的字樣：下一個 session 的第一句話
OPENING='跟上進度'

# ── T1：CLAUDE.md 是 symlink → AGENTS.md 時，不可寫入連結（否則整份規則被覆蓋）
t_symlink() {
  printf '# 規則\n\n- canary ZEBRA-4471 不能消失。\n' > AGENTS.md
  ln -s AGENTS.md CLAUDE.md
  local before; before=$(md5sum < AGENTS.md)
  timeout 600 claude -p "/wrap-up" >/dev/null 2>&1
  [ "$(md5sum < AGENTS.md)" = "$before" ] || { echo "  AGENTS.md 被改動了"; return 1; }
  [ "$(stat -c %F CLAUDE.md)" = "regular file" ] || { echo "  CLAUDE.md 仍是 symlink"; return 1; }
  [ "$(cat CLAUDE.md)" = "@AGENTS.md" ] || { echo "  CLAUDE.md 內容不是指標"; return 1; }
}

# ── T2：CLAUDE.md 有多餘內容時，必須原封全部搬到 AGENTS.md，不可自行篩選
t_no_filter() {
  printf '# 規則\n\n- 既有：canary ZEBRA-4471。\n' > AGENTS.md
  printf '@AGENTS.md\n\n- 重要規則：部署前跑 smoke test。\n- 隨手筆記：xxxx\n- TODO: 之後再整理\n- 廢話一句\n' > CLAUDE.md
  timeout 600 claude -p "/wrap-up" >/dev/null 2>&1
  local k
  for k in "smoke test" "隨手筆記" "TODO" "廢話"; do
    grep -q "$k" AGENTS.md || { echo "  內容遺失：$k"; return 1; }
  done
  [ "$(cat CLAUDE.md)" = "@AGENTS.md" ] || { echo "  CLAUDE.md 未還原為指標"; return 1; }
}

# ── T3：階段一必須「只增不刪」＋「不給第一句話」＋「狀態仍然落地」
#        這條同時驗證兩階段切分與資料不遺失。
t_phase1_boundary() {
  cat > AGENTS.md <<'INNER'
# 規則

- 測試一律放在 tests/ 目錄。
- canary ZEBRA-4471 不能消失。
- 所有測試檔案都要放在 tests/ 底下。
- 一律使用 tabs 縮排。
- 縮排一律使用 spaces，不要用 tabs。
INNER
  printf '@AGENTS.md\n' > CLAUDE.md
  printf '# 舊狀態\n\n> **更新時間**：2026-01-01 09:00\n\nOLDMARK-7788\n' > CURRENT_STATE.md
  local out; out=$(timeout 600 claude -p "/wrap-up" 2>&1)

  # 既有規則一條都不能少（階段一不准刪）
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    grep -qF -- "$line" AGENTS.md || { echo "  階段一刪掉了：$line"; return 1; }
  done < <(grep '^- ' <<'INNER'
- 測試一律放在 tests/ 目錄。
- canary ZEBRA-4471 不能消失。
- 所有測試檔案都要放在 tests/ 底下。
- 一律使用 tabs 縮排。
- 縮排一律使用 spaces，不要用 tabs。
INNER
)
  # 狀態快照仍然要寫入（資料不因等待核准而遺失）
  [ -f CURRENT_STATE.md ] || { echo "  CURRENT_STATE.md 不見了"; return 1; }
  grep -q 'OLDMARK-7788' docs/wrap-up/states/*.md 2>/dev/null \
    || { echo "  上一版快照沒有被封存到 docs/wrap-up/states/"; return 1; }
  # 階段一不可以給第一句話
  grep -q "$OPENING" <<<"$out" && { echo "  階段一就給了第一句話"; return 1; }
  return 0
}

# ── T4：階段二 no-op 路徑 —— 回「都不用改」要維持原樣，且必須給出第一句話
t_phase2_noop() {
  cat > AGENTS.md <<'INNER'
# 規則

- 測試一律放在 tests/ 目錄。
- 所有測試檔案都要放在 tests/ 底下。
- 一律使用 tabs 縮排。
- 縮排一律使用 spaces，不要用 tabs。
INNER
  printf '@AGENTS.md\n' > CLAUDE.md
  local sid; sid=$(uuid)
  timeout 600 claude -p --session-id "$sid" "/wrap-up" > out1.log 2>&1
  local before; before=$(md5sum < AGENTS.md)
  local out2; out2=$(timeout 600 claude -p --resume "$sid" "都不用改，維持原樣" 2>&1 | tee out2.log)
  [ "$(md5sum < AGENTS.md)" = "$before" ] || { echo "  回「都不用改」卻動了 AGENTS.md"; return 1; }
  grep -q "$OPENING" <<<"$out2" || { echo "  階段二沒有給第一句話"; return 1; }
}

# ── T5：階段二核准後，檔案要被搬進 docs/wrap-up/files/ 並保留原始相對路徑
t_phase2_archive_file() {
  printf '# 規則\n\n- canary ZEBRA-4471。\n' > AGENTS.md
  printf '@AGENTS.md\n' > CLAUDE.md
  mkdir -p docs src
  printf '# 舊設計稿\n\nARCHIVEME-3355\n' > docs/old-design-2020.md
  printf 'print("hello")\n' > src/main.py     # 這個不該被搬走
  local sid; sid=$(uuid)
  timeout 600 claude -p --session-id "$sid" "/wrap-up。順帶一提 docs/old-design-2020.md 已經作廢了，不再維護。" > out1.log 2>&1
  timeout 600 claude -p --resume "$sid" "核准封存 docs/old-design-2020.md，其他都不要動。" > out2.log 2>&1
  [ -f docs/wrap-up/files/docs/old-design-2020.md ] \
    || { echo "  檔案沒有被搬到 docs/wrap-up/files/docs/ 並保留路徑"; return 1; }
  [ ! -f docs/old-design-2020.md ] || { echo "  原位置的檔案還在（沒真的搬走）"; return 1; }
  grep -q 'old-design-2020' docs/wrap-up/ARCHIVE.md 2>/dev/null \
    || { echo "  ARCHIVE.md 沒有記錄這次搬移"; return 1; }
  # 反向檢查：不該動的都還在
  [ -f src/main.py ] || { echo "  誤搬了 src/main.py"; return 1; }
  [ -f AGENTS.md ] && [ -f CLAUDE.md ] && [ -f CURRENT_STATE.md ] \
    || { echo "  核心檔案被搬走了"; return 1; }
}

# ── T0：靜態檢查（不呼叫模型）：中英文 SKILL.md 都保有「同一輪核准選單」與「變更前／後」規則
SELFTEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
t_static_menu() { python3 -I "$SELFTEST_DIR/test_skill_approval_menu.py"; }

run "SKILL.md 保有核准選單與變更前後規則（靜態）" t_static_menu
run "symlink 不可被寫入"                t_symlink
run "多餘內容原封搬移、不可篩選"        t_no_filter
run "階段一只增不刪、不給第一句話、狀態仍落地" t_phase1_boundary
run "階段二 no-op：不改動且給第一句話"  t_phase2_noop
run "階段二核准後正確封存檔案"          t_phase2_archive_file
echo "----"; echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
