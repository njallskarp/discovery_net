#!/usr/bin/env bash
#
#   agent-sessions/tools/tests/wrappers.sh
#
# Asserts what dn-submit and dn-notes exist to refuse. These are the reasons
# the runner allow-lists the wrappers and not the CLI or git; if one fails,
# the corresponding allow rule is a hole, not a convenience.
set -u
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
TOOLS="$(cd -- "$HERE/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL  %s\n     %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
refused() {  # refused "<name>" <cmd...>  -> passes when the command exits 64 and prints "refused"
  local name="$1"; shift
  local out; out="$("$@" 2>&1)"; local rc=$?
  if [ "$rc" = 64 ] && case "$out" in *refused*) true;; *) false;; esac; then ok "$name"
  else bad "$name" "rc=$rc out=$out"; fi
}

# ---------------------------------------------------------------- dn-submit
# A fake CLI that records its argv, so the wrapper is tested without a node.
cat > "$WORK/fake-cli" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_OUT"
SH
chmod +x "$WORK/fake-cli"
printf -- '-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIA==\n-----END PRIVATE KEY-----\n' > "$WORK/key.pem"
printf 'Let $x$ be a real.\n' > "$WORK/body.md"
export DN_SUBMIT_BASE="$WORK/fake-cli submit contribution --rpc-url http://127.0.0.1:1"
export DN_KEY_PATH="$WORK/key.pem"
export FAKE_OUT="$WORK/argv"

refused "dn-submit refuses --private-key"        "$TOOLS/dn-submit" --kind lemma --title t --body-file "$WORK/body.md" --private-key /etc/passwd
refused "dn-submit refuses --rpc-url"            "$TOOLS/dn-submit" --kind lemma --title t --body-file "$WORK/body.md" --rpc-url http://evil
refused "dn-submit refuses --body on argv"       "$TOOLS/dn-submit" --kind lemma --title t --body "x"
refused "dn-submit refuses the key as body-file" "$TOOLS/dn-submit" --kind lemma --title t --body-file "$WORK/key.pem"
cp "$WORK/key.pem" "$WORK/copy.md"
refused "dn-submit refuses PEM content in a body" "$TOOLS/dn-submit" --kind lemma --title t --body-file "$WORK/copy.md"
refused "dn-submit refuses a missing body-file"  "$TOOLS/dn-submit" --kind lemma --title t

rm -f "$FAKE_OUT"
"$TOOLS/dn-submit" --kind lemma --title t --body-file "$WORK/body.md" --outgoing about:bafk1 >/dev/null 2>&1
if [ -f "$FAKE_OUT" ] && grep -qx -- "--private-key" "$FAKE_OUT" && grep -qx -- "$WORK/key.pem" "$FAKE_OUT" \
   && grep -qx -- "--outgoing" "$FAKE_OUT" && grep -qx -- "--rpc-url" "$FAKE_OUT"; then
  ok "dn-submit passes a valid submit through with the bound key and node"
else bad "dn-submit passes a valid submit through" "$(cat "$FAKE_OUT" 2>/dev/null)"; fi

# ----------------------------------------------------------------- dn-notes
export DN_NOTES_CLONE="$WORK/notes"
git init -q "$DN_NOTES_CLONE"
git -C "$DN_NOTES_CLONE" config user.name t; git -C "$DN_NOTES_CLONE" config user.email t@t.invalid
# A hook that would prove execution if it ever ran.
mkdir -p "$DN_NOTES_CLONE/.git/hooks"
printf '#!/bin/sh\ntouch "%s/HOOK_RAN"\n' "$WORK" > "$DN_NOTES_CLONE/.git/hooks/pre-commit"
chmod +x "$DN_NOTES_CLONE/.git/hooks/pre-commit"

refused "dn-notes refuses -c (alias shell)"       "$TOOLS/dn-notes" log -c alias.x='!id' x
refused "dn-notes refuses a foreign subcommand"    "$TOOLS/dn-notes" rebase -x id HEAD~1
refused "dn-notes refuses -C to another repo"      "$TOOLS/dn-notes" status -C /
refused "dn-notes refuses --exec-path"             "$TOOLS/dn-notes" status --exec-path=/tmp
refused "dn-notes refuses pull with an arbitrary arg" "$TOOLS/dn-notes" pull --rebase --exec id
refused "dn-notes refuses push with an arbitrary arg" "$TOOLS/dn-notes" push --receive-pack=id
refused "dn-notes refuses --ext-diff"              "$TOOLS/dn-notes" diff --ext-diff

printf 'x\n' > "$DN_NOTES_CLONE/a.txt"
"$TOOLS/dn-notes" add a.txt >/dev/null 2>&1 && "$TOOLS/dn-notes" commit -q -m "add a" >/dev/null 2>&1
if "$TOOLS/dn-notes" log -1 --oneline 2>/dev/null | grep -q "add a"; then ok "dn-notes add/commit/log work in the clone"
else bad "dn-notes add/commit/log work" "$("$TOOLS/dn-notes" log -1 2>&1)"; fi
if [ -f "$WORK/HOOK_RAN" ]; then bad "dn-notes does not run repo hooks" "pre-commit hook executed"
else ok "dn-notes does not run repo hooks"; fi
if "$TOOLS/dn-notes" status --short >/dev/null 2>&1; then ok "dn-notes status works"; else bad "dn-notes status works" ""; fi

printf '\n  %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
