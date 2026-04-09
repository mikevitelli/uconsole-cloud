# Bash completion for uconsole CLI
# Installed to /usr/share/bash-completion/completions/uconsole

_uconsole() {
  local cur prev
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"

  case "$prev" in
    uconsole)
      COMPREPLY=( $(compgen -W "setup link push status logs passwd doctor restore unlink update version help --version --help -v -h" -- "$cur") )
      return 0
      ;;
    logs)
      COMPREPLY=( $(compgen -W "webdash status backup update -f --follow" -- "$cur") )
      return 0
      ;;
  esac

  # After service name in logs, offer follow flag
  if [ "${COMP_WORDS[1]}" = "logs" ] && [ "$COMP_CWORD" -ge 2 ]; then
    COMPREPLY=( $(compgen -W "-f --follow" -- "$cur") )
    return 0
  fi
}

complete -F _uconsole uconsole
