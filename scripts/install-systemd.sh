#!/usr/bin/env bash
# One-time installer: finnspark backend as a systemd service with auto-restart.
# Run with:  sudo bash scripts/install-systemd.sh
set -e
cd "$(dirname "$0")/.."

cp deploy/finnspark-backend.service /etc/systemd/system/finnspark-backend.service

systemctl daemon-reload
systemctl enable finnspark-backend.service

# stop any script-managed instance so the service can bind port 8002
if [ -f backend/logs/backend.pid ]; then
    kill "$(cat backend/logs/backend.pid)" 2>/dev/null || true
    sleep 2
fi

systemctl restart finnspark-backend.service
sleep 2
systemctl --no-pager status finnspark-backend.service | head -12
echo
echo "health check:"
sleep 1
curl -s http://127.0.0.1:8002/api/health/ && echo "  <- OK" || echo "  FAILED — check: journalctl -u finnspark-backend -n 30"
