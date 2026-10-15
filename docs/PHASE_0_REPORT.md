# Phase 0 report: discovery and architecture

**Date:** 2026-10-15 · **Status:** awaiting your review ("Continue" starts Phase 1)

## Delivered

* **Architecture:** `docs/ARCHITECTURE.md` covers the system diagram, the Django app layout,
  multi-tenancy and roles, money rules, integration adapters, the AI assistant design, the
  security alert path, observability and NDPA handling.
* **Data model:** `docs/DATA_MODEL.md` has ERDs for every module, in build order, with
  constraints, encrypted columns and the phase each table arrives in.
* **API outline:** `docs/API.md` lists conventions (auth, org scoping, idempotency, error
  envelope, pagination) and endpoints for every module, webhooks and WebSockets.
* **Decisions:** `docs/adr/0001`–`0005` cover tenancy, no held funds, adapters, the AI assistant
  and auth.
* **Integrations register:** `docs/INTEGRATIONS.md` shows what is verified and what is
  `TODO(verify)`.
* **Environments:** `docs/ENVIRONMENTS.md` covers local, staging and production, configuration,
  and CI.
* **Design tokens:** `packages/design-tokens/` has the source JSON, a generator for the web and
  mobile themes, and **WCAG AA contrast tests**. Documented in `docs/DESIGN_SYSTEM.md`.
* **Skeletons, with no feature code:**
  * **Backend:** Django with settings per environment, health checks (`/health/live`,
    `/health/ready`), the error envelope, request IDs, JSON logging, Sentry hook, ASGI for
    Channels, Celery with a dedicated `alerts` queue, Dockerfile and Compose.
  * **Web:** a React + TypeScript + Tailwind shell that uses the tokens.
  * **Mobile:** an Expo shell that uses the tokens through NativeWind.
* **CI:** `.github/workflows/ci.yml` has four jobs: backend (on Postgres and Redis), web, mobile,
  and design tokens.

## Tested (run here, output shown in chat)

| Check | Result |
|---|---|
| Backend lint and format (ruff) | Clean |
| Backend tests, SQLite and **Postgres 16** | 9 passed on each |
| Migrations up to date; fresh migrate on Postgres | OK |
| `manage.py check --deploy --fail-level WARNING` (production settings) | No issues |
| ASGI app import (HTTP + WebSockets) | OK |
| Web: TypeScript, ESLint, Vitest, production build | Pass (1 test, build 223 kB JS / 70 kB gzip) |
| Mobile: TypeScript, ESLint, Jest | Pass (2 tests) |
| Mobile: Expo bundle for iOS and Android | Builds |
| Design tokens: in sync; 18 contrast and format tests | Pass |
| CI YAML parses; backend CI steps dry-run locally | OK |

## Not tested

* **Docker image build and `docker compose up`.** The Docker daemon isn't available in my
  build environment. Run on your Mac:
  ```bash
  docker compose up -d --build && curl localhost:8001/health/ready
  ```
* **The CI workflow on GitHub itself.** It runs when you push to the new repository.
* **Mobile on a real device or simulator.** Only the bundles were built.
* **The web page in a browser,** visually. Only the build and tests were run.

## Risks

1. **Rent split settlement isn't confirmed.** If gateway subaccounts can't settle directly to
   landlords in the way ADR-0002 assumes, the rent flow needs rethinking, or a licence. Get
   Paystack's written answer early in Phase 1.
2. **WhatsApp costs and template approval.** Meta pricing changes and template review times
   can delay Phase 2. Apply for the WhatsApp Business account and a display name **now**.
3. **SMS for panic fallback.** DND routes and sender-ID approval take time, and burst
   throughput is unproven. Start the Termii (or other provider) sender-ID approval now.
4. **iOS critical alerts** need an Apple entitlement request. Without it, iOS alerts follow
   normal notification rules.
5. **VTU licence.** Confirm that VTU.ng (and a second provider) are licensed before Phase 3.
6. **Solo-developer scope.** The plan is large. The phase gates (paying users before the next
   phase) are the main control.

## Open questions for you

1. **Repository:** create a new GitHub repo, `gintason/homesika` (recommended), and keep
   `gintason/goldia` as an archive, since its bills code is reused in Phase 3?
2. **Launch city:** Lagos or Abuja first? This affects the default timezone, the DisCos for
   electricity and the artisan areas.
3. **Hosting:** DigitalOcean, AWS (Cape Town) or Render/Fly? Needed before the staging deploy in
   Phase 1.
4. **Staff sign-in on the web:** the same OTP plus PIN as mobile, or email and password plus OTP?
5. **Push:** Expo push service (simpler) or direct FCM/APNs (more control)?
6. **SMS provider:** is Termii OK? A second provider for failover?
7. **ID verification provider** for artisans (Phase 4): any preference?
8. **Platform fee on rent:** charge landlords per payment, or subscriptions only at first?
