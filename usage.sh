#!/bin/sh
set -eu
case "$0" in
    */*) script_dir=${0%/*} ;;
    *) script_dir=. ;;
esac
script_dir=$(CDPATH= cd "${script_dir:-/}" && pwd)
for python_command in python3 python; do
    if command -v "$python_command" >/dev/null 2>&1 &&
       "$python_command" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
        exec "$python_command" "$script_dir/codex_usage.py" --chart "$@"
    fi
done
printf '%s\n' 'Python 3.10 or newer is required (python3 or python on PATH).' >&2
exit 1
