# Homesika design system: foundations (Phase 0)

**Source of truth:** `packages/design-tokens/tokens.json`. Running `npm run build` there
generates:
* `web/src/theme/tokens.{js,d.ts,css}`;
* `mobile/src/theme/tokens.{js,d.ts}`.

CI fails if a generated file is out of date or a contrast pair drops below WCAG AA.

## Colour

The colours are sampled from the logo (`brand/homesika-logo.jpg`).

| Role | Token | Hex | Use |
|---|---|---|---|
| Brand navy | `primary.800` | `#0B2B63` | Headers, dark surfaces, logo roof |
| Brand blue | `primary.600` | `#1F4A81` | Primary buttons, links, active states |
| Sky | `sky.200`–`sky.500` | `#A8D8E8`–`#3E86B3` | Highlights, illustrations, charts, selected backgrounds |
| Gold | `gold.400` | `#C4A35A` | **Accent only**: thin dividers, premium/Verified badge, focus details. Never as body text on white |
| Charcoal | `ink.800` | `#2B333D` | Body text (the wordmark colour) |
| Background | `surface.background` | `#F7F9FC` | App background |
| Emergency | `emergency.base` | `#D7261E` | **Reserved for the panic button and live alerts.** Nothing else uses this red |
| Status | `success`, `warning`, `danger` | | Paid / due soon / overdue, errors |

### Measured contrast (WCAG 2.1, all pass AA)

| Pair | Ratio | Needed |
|---|---|---|
| Body text `ink.800` on background | 12.11 | 4.5 |
| Secondary `ink.600` on card | 7.58 | 4.5 |
| Captions `ink.500` on card | 5.43 | 4.5 |
| White on primary button `primary.600` | 8.92 | 4.5 |
| White on header `primary.800` | 13.64 | 4.5 |
| Links `primary.600` on card | 8.92 | 4.5 |
| Gold badge text `gold.700` on `gold.50` | 6.65 | 4.5 |
| Paid / due-soon / overdue badges | 7.18 / 6.91 / 7.37 | 4.5 |
| White on destructive `danger.500` | 5.65 | 4.5 |
| White on panic button / held | 5.02 / 7.36 | 4.5 |
| Input borders `ink.400` on card | 3.07 | 3 (UI) |
| Focus ring `primary.500` on card | 6.05 | 3 (UI) |

## Type

* **Montserrat** for display: headings and amounts. It matches the wordmark's geometric shapes.
* **Inter** for body text, chosen for readability at small sizes on low-end screens.
* **Scale:** 12 / 14 / **16 base** / 18 / 20 / 24 / 30 / 36. The minimum body size on mobile is
  16, so text isn't zoomed or squinted at.

## Layout and touch

* **Spacing:** a 4-point scale (4, 8, 12, 16, 20, 24, 32, 40, 48, 64). Screens use 20 side
  padding on mobile and 24–32 on web.
* **Radius:** 6 for small items, 10 for inputs, 14 for cards, 20 for sheets, pill for chips.
* **Touch targets:** at least **48×48**. The panic button is **132** in diameter, sits in a
  fixed position on estate screens and uses hold-to-trigger with a progress ring.
* **Motion:** 120 / 200 / 320 ms with standard easing. Animations respect "reduce motion" and
  never block input.

## Component library (built at the start of Phase 1, before any screen)

**Shared components:** Button (primary, secondary, ghost, destructive, loading), TextField
(label, hint, error), MoneyInput, PhoneInput, OTP code input, PIN pad, Select / sheet picker,
Card, ListRow, Badge (status), Avatar, EmptyState, Skeleton, Banner (error, offline), Toast,
Dialog / confirm sheet, Stepper, Tabs, DataTable (web), Chart wrappers (web), **PanicButton**
(hold-to-trigger, silent toggle, alert-type sheet).

**Rules for every component:**
* accessible labels and roles;
* visible focus on web;
* text that scales to 200% without clipping;
* a skeleton state;
* an error state with a retry;
* plain-language copy, available in English and Pidgin.

**Weak networks:**
* optimistic UI only for safe actions;
* an offline banner;
* cached reads;
* retry with backoff.

The panic button never waits on the network to show its confirmation. It queues the alert and
retries, and the SMS fallback is triggered server-side.
