# finnspark — Accelerator & Investment Platform

finnspark is a modern, full-featured accelerator and investment management platform for the finnpact brand,
on the finnpayments stack: **FastAPI + SQLAlchemy + SQLite (DATABASE_URL-driven) backend ·
React 18 + Vite frontend · systemd + nginx deployment.**

The brand mark (rounded blue tile + amber spark bolt with ignition dots) lives in
`frontend/public/logo.svg` / `favicon.svg` and inline as `frontend/src/components/Logo.jsx`.

## What is implemented

| Spec area | Status |
|---|---|
| Multi-tenancy (Organization → Branch), branch switcher | ✅ |
| JWT auth (**corrected**: no secrets in token payload, scrypt password hashes, refresh in httpOnly cookie) | ✅ |
| RBAC: constant roles + custom roles with granular permissions, server-side enforcement on every endpoint | ✅ |
| Selection Board: stages (configurable), filters, statuses (Invited/In Selection/Rejected/Archived), evaluator scoring → average score, invite-to-register | ✅ |
| Forms builders: application forms (10 field types incl. file/date/number), scoring forms (weighted, `is_for_graduation`), investment forms | ✅ |
| Public apply page (`/apply/:formId`) → creates Applicant | ✅ |
| Programs: types, cohorts, enrolled businesses, graduation toggle, mentor assignment, Invest action, Excel export | ✅ |
| LMS: courses → modules → lessons → content blocks (video/text/image/file/quiz), enrollment + per-user progress tracking | ✅ |
| Library: branch/program/business documents upload & download | ✅ |
| Investment: Dealflow (stages/tiers/rounds), Approval (multi-level committees, decisions), Portfolio management | ✅ |
| Reports pack: 11 detailed-info sections + portfolio snapshot, payments schedule, aging analysis, forex — all paginated + Excel export | ✅ |
| Dashboards: program funnel/tiles/distributions + investment/learning/team views | ✅ |
| Collaboration: announcements (+reactions), shared calendar (public/private), chat (polling), notifications bell | ✅ |
| i18n: `/en/api/...` style prefix supported, multilingual form names (i18n JSON columns), RTL-ready UI language switcher (EN/AR) | ✅ |
| Chat real-time | Polling (spec allows; no websocket lib installed system-wide) |

## Layout

```
finnspark/
├── backend/
│   ├── run.py                  # entrypoint (PORT=8002, binds 127.0.0.1)
│   ├── app/
│   │   ├── main.py             # FastAPI app; routers under /api and /{lang}/api
│   │   ├── models.py           # full §7 data model
│   │   ├── security.py         # scrypt hashing, JWT (no secrets in payload)
│   │   ├── deps.py             # auth, RBAC + tenant guards, role→permission map
│   │   ├── seed.py             # OCIF-style demo data (80 applicants / 79 businesses)
│   │   └── routers/            # auth, references, tenancy, forms, selection,
│   │                           # programs, courses, library, investment,
│   │                           # collaboration, dashboards, reports
│   ├── media/uploads/          # uploaded files (never in the DB)
│   └── finnspark.db    # SQLite (DATABASE_URL-driven → Postgres drop-in)
├── frontend/
│   ├── src/pages/              # one page per §4 route (same client routes as original)
│   ├── dist/                   # production build (served by nginx)
│   └── vite.config.js          # dev proxy /api,/auth,/media → :8002
├── scripts/                    # start/stop helpers for local runs
└── deploy/                     # systemd unit + nginx site
```

## Run locally

```bash
scripts/start-backend.sh     # seeds demo DB on first run
```

Open **http://127.0.0.1:8002** — the backend serves both the API and the built React app
(SPA history-fallback), so a single port gives you the whole system.
Alternatively run the Vite dev server (`scripts/start-frontend.sh`, port 3002, proxy configured).

> Note: the refresh-token cookie is issued with the `Secure` flag only when the request
> arrives over HTTPS (directly or via nginx `X-Forwarded-Proto`), so sessions survive page
> reloads on plain-HTTP local setups too.

Demo logins (seeded): `admin@finnpact.jo / Admin123!` (branch admin),
`investments@finnpact.jo / Admin123!` (investment manager),
`mentor1@finnpact.jo / Demo123!`, `founder1@startup.jo / Demo123!`.

## Deploy on the VPS (spec §13)

```bash
# backend service
sudo cp deploy/finnspark-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now finnspark-backend

# frontend static build (option A — recommended)
cd frontend && npm run build

# nginx site + TLS
sudo cp deploy/nginx-accelerate.finnverify.com /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/nginx-accelerate.finnverify.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d accelerate.finnverify.com      # after DNS A record exists
```

Set a strong `JWT_SECRET` in the systemd unit before going live.

## Security features (spec §9.1)

- Secure JWT Authentication: Tokens carry only `user_id`, `branch_id`, roles, type, expiry.
- Passwords stored as **scrypt hashes**, never plaintext.
- Refresh token delivered as an **httpOnly Secure SameSite cookie** scoped to `/api/auth`.
- Every list endpoint re-authorises the caller against the target branch server-side.
