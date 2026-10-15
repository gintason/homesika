#!/bin/sh
set -e
# Only the api container migrates; workers and beat set SKIP_MIGRATIONS=1 and wait for it.
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  python manage.py migrate --noinput
fi
exec "$@"
