# Homesika

AI-powered property and everyday-life platform for Nigeria (expanding across Africa): rent,
bills, maintenance and estate security for landlords, agents, tenants, estates and artisans, with
WhatsApp as the front door. Built by **Homesika Real Estate**.

| Folder | What | Stack |
|---|---|---|
| `backend/` | API, webhooks, WebSockets, background jobs | Python 3.13, Django 5.2, DRF, PostgreSQL 16, Redis 7, Celery, Channels |
| `web/` | Dashboard for landlords, agents, estates, admins | React 19 + TypeScript, Vite, Tailwind |
| `mobile/` | App for tenants, residents, artisans, security | React Native (Expo SDK 57), NativeWind |
| `packages/design-tokens/` | Single source of colours, type, spacing (WCAG-tested) | JSON + generator |
| `docs/` | Architecture, data model, API, integrations, decisions | Markdown + Mermaid |

**Start with:** `docs/ARCHITECTURE.md` → `docs/DATA_MODEL.md` → `docs/API.md` (contract: `docs/openapi.yaml`).
Assistant: `docs/ASSISTANT.md`. Deploying: `docs/DEPLOY_RENDER.md`. Phase reports: `docs/PHASE_*_REPORT.md`.

## Run locally (Mac)

**Backend** (needs Docker Desktop running):
```bash
cp backend/.env.example backend/.env    # then set DJANGO_SECRET_KEY
docker compose up -d --build
curl http://localhost:8001/health/ready
```
API docs: http://localhost:8001/api/v1/docs/. The ports (5434, 6381, 8001) don't clash with the
Goldia stack.

**Web:**
```bash
cd web && cp .env.example .env.local && npm install && npm run dev   # http://localhost:5173
```

**Mobile:**
```bash
cd mobile && cp .env.example .env && npm install && npx expo start
```

**Design tokens** (after editing `packages/design-tokens/tokens.json`):
```bash
cd packages/design-tokens && npm run build && npm test
```

## Checks (the same as CI)

```bash
cd backend && pip install -r requirements/dev.txt && ruff check . && pytest
cd backend && python manage.py assistant_eval --limit 5   # assistant evaluation (mock model unless ASSISTANT_PROVIDER=anthropic)
cd web && npm run check && npm run build
cd mobile && npm run check
cd packages/design-tokens && npm run check && npm test
```

## Rules we build by

* Multi-tenant from day one.
* Money stored as integer kobo.
* Signed, idempotent webhooks.
* **No stored wallet or held funds** until legal approval is confirmed in writing.
* Every third party behind an interface, with a labelled mock; unverified details are marked
  `TODO(verify)`.
* Tests for every feature.
* No secrets in the repo.
* NDPA-compliant data handling.

See `docs/adr/` for the reasoning.
