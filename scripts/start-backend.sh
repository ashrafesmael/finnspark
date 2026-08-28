#!/usr/bin/env bash
# Start the FinnSpark backend (dev helper).
set -e
cd "$(dirname "$0")/../backend"
mkdir -p logs media/uploads
# SMTP credentials (same Gmail account as finnverify)
set -a; [ -f .env ] && . .env; set +a

export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://accelerate.finnpact.com}"
if [ ! -f finnspark.db ]; then
    echo "Seeding database..."
    PYTHONPATH=. python3 app/seed.py
fi
if curl -s -m 2 http://127.0.0.1:8002/api/health/ >/dev/null 2>&1; then
    echo "Backend already running on 127.0.0.1:8002"
    exit 0
fi
setsid nohup python3 run.py >> logs/boot.log 2>&1 < /dev/null &
echo $! > logs/backend.pid
sleep 1
echo "Backend starting on 127.0.0.1:8002 (pid $(cat logs/backend.pid))"
