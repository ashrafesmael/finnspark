server {
    listen 80;
    server_name accelerate.finnverify.com;

    # --- API, auth, websockets, media -> FastAPI (127.0.0.1:8002) ---
    location ~ ^/(api|auth|ws|media)/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # websocket upgrade for /ws (chat/notifications)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 200m;
    }

    # --- Frontend: built static bundle (spec §13.3 option A) ---
    root /home/administrator/finnspark/frontend/dist;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }   # SPA history-fallback

    access_log /var/log/nginx/accelerate.access.log;
    error_log  /var/log/nginx/accelerate.error.log;
}
