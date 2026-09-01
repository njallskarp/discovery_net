# Shared prompting helpers. Sourced, not executed.
# Setup is the one place a human is present, so it is the one place worth
# spending their attention on validation.

die()  { printf '\n  %s\n\n' "$*" >&2; exit 1; }
say()  { printf '%s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
ok()   { printf '    ok: %s\n' "$*"; }
bad()  { printf '    problem: %s\n' "$*"; }

require_tty() {
  [ -t 0 ] || die "$1 is interactive and needs a terminal.
  It is a setup step, not something a timer runs."
}

# ask VAR "question" [default]
ask() {
  __var="$1"; __q="$2"; __def="${3:-}"
  while :; do
    if [ -n "$__def" ]; then printf '%s [%s]: ' "$__q" "$__def"
    else                     printf '%s: ' "$__q"; fi
    IFS= read -r __ans || die "input closed"
    [ -z "$__ans" ] && __ans="$__def"
    [ -n "$__ans" ] && break
    bad "this one has no default; please answer"
  done
  eval "$__var=\$__ans"
}

# ask_choice VAR "question" "a b c" [default]
ask_choice() {
  __var="$1"; __q="$2"; __opts="$3"; __def="${4:-}"
  while :; do
    ask __c "$__q ($(echo "$__opts" | tr ' ' '/'))" "$__def"
    for __o in $__opts; do
      if [ "$__c" = "$__o" ]; then eval "$__var=\$__c"; return 0; fi
    done
    bad "pick one of: $__opts"
  done
}

confirm() {   # confirm "question" -> 0 yes / 1 no
  while :; do
    printf '%s [y/n]: ' "$1"
    IFS= read -r __y || return 1
    case "$__y" in [yY]*) return 0;; [nN]*) return 1;; esac
  done
}

write_env() {  # write_env <path> <<'EOF' ... EOF
  __path="$1"
  if [ -e "$__path" ]; then
    say ""
    confirm "  $__path exists. Overwrite?" || die "left alone. Nothing written."
  fi
  mkdir -p "$(dirname "$__path")"
  cat > "$__path"
  chmod 600 "$__path"
  say ""
  say "  wrote $__path (mode 600)"
}
