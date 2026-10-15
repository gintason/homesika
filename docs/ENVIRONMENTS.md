# Environments and configuration

| | Local | Staging | Production |
|---|---|---|---|
| Purpose | Development on your Mac | Pilot testing with sandbox keys, demo to landlords | Real users |
| Django settings | `config.settings.local` | `config.settings.staging` | `config.settings.production` |
| Run with | `docker compose up` | Same images, deployed by CI from `main` | Same images, deployed by tagged release |
| Database / Redis | Containers | Managed Postgres 16 + Redis 7 | Managed Postgres 16 (PITR backups) + Redis 7 |
| Payments, SMS, WhatsApp, VTU | Mock adapters by default; sandbox keys optional | Provider **sandbox/test** keys | Live keys |
| Claude API | Mock by default; real key optional | Real key, low cost cap | Real key, production caps |
| Error tracking | Console | Sentry (staging project) | Sentry (production project) |
| Debug tools | API docs, Django debug | API docs (protected) | Off |

* **All configuration comes from environment variables** (12-factor). Each app has a
  `.env.example` listing every variable with safe placeholders; real `.env` files are
  gitignored. Secrets in staging and production live in the host's secret manager, never in
  the repo or the image.
* **The same Docker image** is promoted from staging to production. Only env vars differ.
* **Hosting is an open question:** e.g. DigitalOcean (Lagos-friendly latency via Frankfurt or
  London), AWS `af-south-1` (Cape Town), or Render/Fly. Choose before the Phase 1 deploy.
* **Mobile:** EAS build profiles `development`, `preview` (pointing at staging) and
  `production`. `EXPO_PUBLIC_API_URL` is set per profile.
* **Web:** `VITE_API_URL` per environment; built static files served from a CDN.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | Steps |
|---|---|
| `backend` | Ruff lint and format check, migrations up to date, `manage.py check --deploy` against production settings, pytest against **Postgres 16 + Redis 7** service containers |
| `web` | `npm ci`, ESLint, TypeScript, Vitest, production build |
| `mobile` | `npm ci`, TypeScript, ESLint, Jest |
| `design-tokens` | Token build is in sync with the committed outputs; WCAG contrast tests |

Deployment jobs (build image, push to registry, deploy to staging and production) are added in
Phase 1 once you've chosen hosting.
