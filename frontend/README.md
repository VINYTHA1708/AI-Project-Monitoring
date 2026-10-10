# Faculty project dashboard

React + Vite frontend for the FastAPI project-monitoring backend. The faculty
dashboard loads assigned projects, project progress, submissions, and document
analysis from the API.

## Local development

Requirements: Node.js and npm.

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

Open the local URL printed by Vite. In development, Vite proxies API requests
through `/api` to `VITE_API_BASE_URL` and removes that prefix before forwarding
them to FastAPI. The backend must be running. If it uses another local address,
set that address as `VITE_API_BASE_URL` before starting Vite. This variable is
an API address, not a secret.

To keep a local setting across terminal sessions, put it in
`frontend/.env.local`; do not commit local environment files. Vite reads
`VITE_`-prefixed variables.

## Production build and deployment

Set `VITE_API_BASE_URL` to the deployed API origin **before** building:

```powershell
cd frontend
$env:VITE_API_BASE_URL = "https://api.example.edu"
npm ci
npm run build
```

Deploy the generated `frontend/dist/` directory to a static web host configured
to serve `index.html` for the application route. The API URL is embedded in the
build; changing a hosting environment variable after building does not change
it, so rebuild when the API origin changes. Do not use the default
`http://127.0.0.1:8000` for a deployed frontend: in a user's browser,
`127.0.0.1` refers to that user's own device.

The backend currently does not register CORS middleware. If the frontend and
API use different origins, configure a reviewed backend CORS policy that allows
the exact frontend origin and the required methods and headers (including
`Authorization` for authenticated API calls), then restart and verify the API.
Alternatively, configure your host's reverse proxy to route the backend API
paths to FastAPI on the same origin as the frontend. Use HTTPS for deployed
frontend and API traffic.

Frontend variables prefixed with `VITE_` are public and bundled into browser
code. Never put passwords, API keys, JWT/OTP secrets, or other private
credentials in them. On the backend host, configure `DATABASE_URL`, the SMTP
settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and
`SMTP_FROM_EMAIL`), and the authentication settings shown in
`backend/.env.example`. Production authentication requires `APP_ENV=production`,
non-empty `STUDENT_EMAIL_DOMAINS` and `FACULTY_EMAIL_ALLOWLIST`, and separate,
unique `JWT_SECRET_KEY` and `OTP_HMAC_SECRET` values of at least 32 bytes.
Provide working SMTP delivery for verification codes. Keep these backend
credentials on the server; never put them in frontend variables.

For the authentication schema preflight, migration, and recovery procedure,
see `backend/migrations/README.md`; do not substitute `init_db.py` for the
authentication migration. When deploying behind a reverse proxy, follow that
guide's trusted-proxy requirements for client IP handling.

## Faculty sign-in and access

Faculty registration requires an email allowed by the backend's institutional
faculty configuration and a working SMTP setup to receive the registration
verification code. After verifying registration, sign in with the password and
complete a separate login code check. The dashboard is for faculty accounts;
student accounts are not admitted. Faculty must also be approved and assigned
to projects to access their data. Project assignment is documented by the
backend provisioning script and must be performed against the configured
backend database by an authorized operator.

The access token is held in browser memory only, not local or session storage.
Refreshing the page clears it and requires signing in again. Authentication
will not be ready until the reviewed backend migration has been applied and the
backend's database, email, allowlist, and production authentication settings
are configured.

## Tests

Run the frontend tests and production build from `frontend/`:

```powershell
npm test
npm run build
npm run preview
```

`npm run preview` serves the generated build locally for a deployment smoke
check. Authentication UI tests mock the API; they do not connect to a live
backend or persist or send a real bearer token.
