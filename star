#!/bin/sh
# Alter Name, bleibt als Alias fuer pitwall
exec "$(cd "$(dirname "$0")" && pwd)/pitwall" "$@"
