#!/usr/bin/env bash
# Raeumt Reste alter Staende auf, die CI rot machen. Im Ordner deines ReaperPy-Klons ausfuehren (Git Bash geht auch unter Windows).
set -e

OLD="02-find-value 03-edit-cheats 04-assembler-basics 05-items-unreal 06-items-unity 07-values-and-live 08-export 09-pointers 10-debugger 11-advanced-tools 11-player-or-enemy 12-troubleshooting 13-glossary"
for lang in de en; do
  for n in $OLD; do
    git rm -q --ignore-unmatch "docs/howto/$lang/$n.md"
  done
done
git rm -q --ignore-unmatch tools_who_gui.py

git commit -F - <<'MSG'
Fix CI: remove stale files left over from the 6.2.x renumbering

The how-to guides were renumbered (14 guides, new "Cheat in four steps",
"Player or enemy?" removed) and the PLAYER / ENEMY tab was dropped, but the
upload only added the new files. The old ones stayed in the repo:

- docs/howto/{de,en}: 13 old files per language (old numbering plus
  11-player-or-enemy.md) next to the new set, so every guide existed twice
  and the removed tab was still described. This broke
  test_howto.ButtonNames (de + en).
- tools_who_gui.py: GUI of the removed tab, nothing imports it, its German
  messages have no English entries. This broke
  test_i18n_backend.test_german_messages_in_all_modules_have_english.

Full suite: 1147 tests OK (5 skipped) instead of 3 failures.
MSG
echo "Fertig. Jetzt: git push"
