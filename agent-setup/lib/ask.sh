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
#
# Every temp here is prefixed __ac_. ask() writes to __var/__q/__def/__ans, and
# shell variables are global: an earlier version reused those names, so the
# nested ask() overwrote __var and ask_choice assigned to its own scratch
# variable instead of the caller's. The caller then read an unset variable.
ask_choice() {
  __ac_var="$1"; __ac_q="$2"; __ac_opts="$3"; __ac_def="${4:-}"
  while :; do
    ask __ac_ans "$__ac_q ($(echo "$__ac_opts" | tr ' ' '/'))" "$__ac_def"
    for __ac_o in $__ac_opts; do
      if [ "$__ac_ans" = "$__ac_o" ]; then eval "$__ac_var=\$__ac_ans"; return 0; fi
    done
    bad "pick one of: $__ac_opts"
  done
}

confirm() {   # confirm "question" -> 0 yes / 1 no
  while :; do
    printf '%s [y/n]: ' "$1"
    IFS= read -r __y || return 1
    case "$__y" in [yY]*) return 0;; [nN]*) return 1;; esac
  done
}

# q VALUE -> a single-quoted shell literal. Bindings are sourced, so every value
# written into one is shell; a path with a space or a quote would otherwise be
# a syntax error at the next tick, or worse, a command.
q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

# env_get FILE KEY -> the value KEY has after sourcing FILE, in a subshell.
# The bindings are quoted by q(), so grep|cut would return the quotes.
env_get() { ( set +u; . "$1" >/dev/null 2>&1; eval "printf '%s' \"\${$2:-}\"" ); }

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
