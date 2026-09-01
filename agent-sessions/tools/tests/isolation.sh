#!/usr/bin/env bash
#
#   agent-sessions/tools/tests/isolation.sh
#
# Asserts the properties dn-compute exists to provide. These are not unit tests of
# a helper; they are the security boundary that makes granting an interpreter to
# an unattended agent holding a signing key defensible. If any of them fail, the
# grant is not safe and the allow rule should come back out.
set -u
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
COMPUTE="$HERE/../dn-compute"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %s\n     %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }

# 1. It has to actually be useful, or none of the rest matters.
cat > "$WORK/calc.py" <<'PY'
from sympy import Rational, nsimplify
print("EXACT:", Rational(1, 3) + Rational(1, 4))
print("DELTA:", nsimplify(0.25))
PY
out="$("$COMPUTE" "$WORK/calc.py" 2>&1)"
case "$out" in *"EXACT: 7/12"*) ok "exact rational arithmetic works" ;;
                *) bad "exact rational arithmetic works" "$out" ;; esac

# 2. The one that matters most. Python has sockets; the allow list cannot take
#    them away, so the network namespace has to.
cat > "$WORK/net.py" <<'PY'
import socket
try:
    socket.create_connection(("1.1.1.1", 53), timeout=4)
    print("NETWORK: REACHABLE")
except Exception as exc:
    print("NETWORK: blocked ->", type(exc).__name__)
PY
out="$("$COMPUTE" "$WORK/net.py" 2>&1)"
case "$out" in *"NETWORK: blocked"*) ok "no network egress" ;;
                *) bad "no network egress" "$out" ;; esac

# 3. The signing key is the asset. It must not be reachable even by absolute path.
cat > "$WORK/key.py" <<'PY'
import pathlib
hits = [str(p) for p in pathlib.Path("/").glob("**/contributor.pem")]
print("KEYS_VISIBLE:", len(hits))
PY
out="$("$COMPUTE" "$WORK/key.py" 2>&1)"
case "$out" in *"KEYS_VISIBLE: 0"*) ok "signing keys not reachable" ;;
                *) bad "signing keys not reachable" "$out" ;; esac

# 4. A firing has a deadline; a runaway computation must not eat it.
cat > "$WORK/spin.py" <<'PY'
while True:
    pass
PY
start=$(date +%s)
DN_COMPUTE_TIMEOUT=5 "$COMPUTE" "$WORK/spin.py" >/dev/null 2>&1
elapsed=$(( $(date +%s) - start ))
if [ "$elapsed" -lt 25 ]; then ok "runaway script killed (${elapsed}s)"
else bad "runaway script killed" "took ${elapsed}s"; fi

# 5. Nothing the script writes may persist into the agent's working tree.
cat > "$WORK/write.py" <<'PY'
try:
    open("/work/escaped.txt", "w").write("x")
    print("WROTE_TO_WORK")
except Exception as exc:
    print("WORK_READONLY ->", type(exc).__name__)
PY
out="$("$COMPUTE" "$WORK/write.py" 2>&1)"
if [ -f "$WORK/escaped.txt" ]; then bad "work dir is read-only" "script created $WORK/escaped.txt"
else case "$out" in *WORK_READONLY*) ok "work dir is read-only" ;;
                    *) bad "work dir is read-only" "$out" ;; esac; fi

# 6. Unprivileged, so a mount or kernel mistake is not immediately root.
cat > "$WORK/who.py" <<'PY'
import os
print("UID:", os.getuid())
PY
out="$("$COMPUTE" "$WORK/who.py" 2>&1)"
case "$out" in *"UID: 65534"*) ok "runs unprivileged (nobody)" ;;
                *) bad "runs unprivileged (nobody)" "$out" ;; esac

printf '\n  %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
