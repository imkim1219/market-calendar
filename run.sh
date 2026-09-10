#!/bin/bash
# launchd entry point: load secrets, regenerate the ics, log everything.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
exec /usr/bin/env python3 build_ics.py >> build.log 2>&1
