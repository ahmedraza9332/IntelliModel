# Google Sign-In and user database — setup checklist

This document describes the optional auth feature (SQLite + session cookie + Google ID tokens), what was added to the repo, and how to verify it.

---

## What was implemented (summary)

1. **Backend auth package** (`backend/auth/`) — SQLite tables `users` and `sessions`, upsert users keyed by Google `sub`, opaque session tokens with expiry.
2. **API** (`backend/api_server.py`) — Startup migration via lifespan; routes under `/api/auth/*`; CORS allowlist (not `*`) so browsers send cookies; `load_dotenv(backend/.env)`.
3. **Dependencies** — `google-auth` (Python), `@react-oauth/google` (npm).
4. **Frontend** — `GoogleOAuthProvider` when `VITE_GOOGLE_CLIENT_ID` is set; API client uses `credentials: "include"`; Navbar shows sign-in / profile / sign-out.

Pipeline ML routes are **not** gated on login unless you add that separately.

---

## Files added

| Path | Purpose |
|------|---------|
| `backend/auth/__init__.py` | Package marker |
| `backend/auth/db.py` | SQLite schema + user/session helpers |
| `backend/auth/router.py` | `POST /api/auth/google`, `GET /api/auth/me`, `POST /api/auth/logout` |
| `backend/.env.example` | Copy to `backend/.env` — `GOOGLE_OAUTH_CLIENT_ID`, optional CORS/SQLite/secure cookie |
| `Frontend/.env.example` | `VITE_API_BASE_URL`, `VITE_GOOGLE_CLIENT_ID` |

The SQLite database file is created at runtime (default: `backend/data/intellimodel_users.db`), not shipped in git.

---

## Files changed (existing)

| File | Change |
|------|--------|
| `backend/api_server.py` | Auth routes in docstring; `load_dotenv`; lifespan `init_db`; CORS env; `include_router(auth)` |
| `backend/requirements.txt` | `google-auth>=2.29.0` |
| `backend/QUICK_START.md` | Google auth section (+ link here) |
| `Frontend/package.json` | `@react-oauth/google` |
| `Frontend/src/main.tsx` | `GoogleOAuthProvider` when client ID set |
| `Frontend/src/api/client.ts` | `credentials: "include"`; `signInWithGoogle`, `getAuthMe`, `logoutAuth`, `AuthUser` |
| `Frontend/src/components/landing/Navbar.tsx` | Google button, session restore, avatar, sign out |
| `Frontend/src/vite-env.d.ts` | `VITE_*` typings |

---

## What you must do locally

1. **Google Cloud Console** — APIs & Services → Credentials → **OAuth 2.0 Client ID** (type **Web application**). Under the client, add **Authorized JavaScript origins** for your dev URL, e.g. `http://localhost:5173`.

2. **`backend/.env`** — Copy `backend/.env.example` to `backend/.env` and set:
   - `GOOGLE_OAUTH_CLIENT_ID` — your Web client ID (ends with `.apps.googleusercontent.com`).

3. **`Frontend/.env.local`** — Copy from `Frontend/.env.example` if needed. Set:
   - `VITE_GOOGLE_CLIENT_ID` — **same** value as `GOOGLE_OAUTH_CLIENT_ID`.

4. **Install dependencies** (if not already):
   - Backend: `py -m pip install -r requirements.txt` (from `backend/`).
   - Frontend: `npm install` (from `Frontend/`).

5. **Optional env vars** (backend `.env`):
   - `INTELLIMODEL_CORS_ORIGINS` — comma-separated origins (defaults include `http://localhost:5173`).
   - `INTELLIMODEL_SQLITE_PATH` — override SQLite path.
   - `INTELLIMODEL_COOKIE_SECURE=true` — in production over HTTPS.

6. **Git hygiene** — Add `.env` and local `*.db` to `.gitignore` if you use git, so secrets and local DBs are not committed.

---

## Auth API (reference)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/google` | Body: `{ "credential": "<Google ID token JWT>" }`. Verifies token, upserts user, sets HTTP-only cookie `im_session`. |
| `GET` | `/api/auth/me` | Returns current user JSON or `401`. |
| `POST` | `/api/auth/logout` | Deletes server session and clears cookie. |

---

## How to verify

### A. Frontend build

```powershell
cd Frontend
npm run build
```

Expect a successful production build.

### B. API health

```powershell
cd backend
python api_server.py
```

In browser or curl: `http://localhost:9000/api/health` → JSON with `"status": "ok"` (and `active_jobs`).

### C. Auth endpoints (after `GOOGLE_OAUTH_CLIENT_ID` is set)

- `GET http://localhost:9000/api/auth/me` with no cookie → **401**.
- After signing in through the UI, same request with cookies → **200** and user fields.

### D. Browser end-to-end

1. Start API (`python api_server.py` in `backend`) and Vite (`npm run dev` in `Frontend`).
2. Open `http://localhost:5173` (or the origin you put in Google Console and CORS).
3. If `VITE_GOOGLE_CLIENT_ID` is set, the navbar shows Google Sign-In.
4. Sign in → success toast → avatar / name.
5. DevTools → **Application** → **Cookies** → look for **`im_session`** on requests to port **9000**.
6. DevTools → **Network** → `GET /api/auth/me` → **200** when logged in.
7. Sign out → `GET /api/auth/me` → **401** again.

### E. SQLite file

After a successful login, check `backend/data/intellimodel_users.db` (unless overridden) with any SQLite browser; tables `users` and `sessions` should have rows.

---

## Troubleshooting

- **CORS errors** — Ensure your page origin is listed in `INTELLIMODEL_CORS_ORIGINS` (or use the default that includes `localhost:5173`).
- **`503` on `/api/auth/google`** — `GOOGLE_OAUTH_CLIENT_ID` missing in `backend/.env` or not loaded (restart server after editing `.env`).
- **Google popup / button errors** — Authorized JavaScript origins in Google Cloud must match the URL in the address bar (scheme + host + port).
- **Cookie not sent** — Frontend must call the API with `credentials: "include"` (already default in `client.ts`). API must use explicit CORS origins with `allow_credentials=True` (already configured).
