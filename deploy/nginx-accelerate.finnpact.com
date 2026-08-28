server {
    listen 80;
    server_name accelerate.finnpact.com;

    # --- API, auth, media -> finnspark FastAPI (127.0.0.1:8002) ---
    location ~ ^/(api|auth|ws|media)/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 200m;
    }

    # --- Frontend: built static bundle with SPA history-fallback ---
    root /home/administrator/finnspark/frontend/dist;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }

    access_log /var/log/nginx/accelerate.access.log;
    error_log  /var/log/nginx/accelerate.error.log;
}
