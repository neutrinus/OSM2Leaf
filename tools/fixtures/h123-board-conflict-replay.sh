#!/usr/bin/env bash
# H123: replay a two-branch conflict in TODO.md and claims.md and resolve it by ID.
# Run from the repo root: bash tools/fixtures/h123-board-conflict-replay.sh
set -e
REPO=$(pwd)
BOARD=${BOARD:-$REPO/tools/board.py}
BASE=c4b5a90                                  # origin/main when H123 started
W=$(mktemp -d); git worktree add -q --detach "$W/wt" "$BASE"; cd "$W/wt"
B="python3 $BOARD --todo TODO.md --claims docs/research/claims.md"
SEC='M4.35 — `class_code` is the TMC location type: second country and reference test (C-3200–C-3209)'
printf -- '- [ ] **M9.63 — side A**\n  - Status: open · Owner: — · Critical: no\n  - Depends: —\n  - Goal: a.\n  - Done when: a.\n  - Claims: C-6590–C-6599\n' > "$W/a.md"
printf -- '- [ ] **M9.64 — side B**\n  - Status: open · Owner: — · Critical: no\n  - Depends: —\n  - Goal: b.\n  - Done when: b.\n  - Claims: C-6600–C-6609\n' > "$W/b.md"
git checkout -q -b replay-a
$B add-task "$W/a.md"; $B add-claims --section "$SEC" --row '| C-3205 | side A | OBSERVED | M | x |'; $B claim H122 --owner A
git commit -qam A
git checkout -q -b replay-b "$BASE"
$B add-task "$W/b.md"; $B add-claims --section "$SEC" --row '| C-3206 | side B | OBSERVED | M | y |'; $B claim H121 --owner B; $B done H122 --result "B closed it"
git commit -qam B
git checkout -q replay-a
$B lost --base replay-b --head replay-a || echo "lost (ours vs theirs) exit $?"
git merge -q replay-b || true
grep -c '^<<<<<<<' TODO.md docs/research/claims.md || true
$B resolve TODO.md || echo "resolve TODO.md exit $?"
$B resolve docs/research/claims.md; echo "resolve claims.md exit $?"
grep -c '^<<<<<<<' TODO.md docs/research/claims.md || true
grep -n '^- \[.\] \*\*M9.6[34]\|Owner: B' TODO.md | cut -c1-60
grep -n '^| C-320[56]' docs/research/claims.md | cut -c1-40
python3 tools/claims_check.py | tail -1
$B lost --base replay-a; echo "lost vs A exit $?"; $B lost --base replay-b; echo "lost vs B exit $?"
cd "$REPO"; git worktree remove --force "$W/wt"; git branch -D -q replay-a replay-b
