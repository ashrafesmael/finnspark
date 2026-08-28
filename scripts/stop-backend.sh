#!/usr/bin/env bash
# Stop the finnspark backend (dev helper).
PIDFILE="$(dirname "$0")/../backend/logs/backend.pid"
if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null && echo "Stopped $(cat "$PIDFILE")" || echo "Not running"
    rm -f "$PIDFILE"
else
    echo "No pidfile; is it running?"
fi
