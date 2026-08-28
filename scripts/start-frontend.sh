#!/usr/bin/env bash
# Start the FinnSpark frontend dev server (option B of spec §13.3).
set -e
cd "$(dirname "$0")/../frontend"
if curl -s -m 2 -o /dev/null http://127.0.0.1:3002/ 2>/dev/null; then
    echo "Frontend already running on 127.0.0.1:3002"
    exit 0
fi
setsid nohup npm run dev >> ../backend/logs/frontend.log 2>&1 < /dev/null &
echo $! > /tmp/va-frontend.pid
echo "Frontend dev server starting on 127.0.0.1:3002"
