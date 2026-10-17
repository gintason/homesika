import { useState } from "react";

import {
  Card,
  DataTable,
  LoadingBlock,
  PageHeader,
  Select,
  StatCard,
} from "../../components";
import { fmt, strings } from "../../i18n";
import { formatMonth } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useOrgQuery } from "../../lib/queries";
import type {
  Analytics as AnalyticsData,
  AnalyticsMonth,
} from "../../lib/types";
import { QueryState } from "../shared";

const t = strings.analytics;
const PERIODS = ["3", "6", "12"] as const;

// Chart-only colours, checked with the dataviz palette validator (lightness, chroma, colour-blind
// separation, contrast on white): billed = brand primary.500, collected = a chart amber (not the
// reserved warning colour). Identity also comes from the legend and the table, never colour alone.
const SERIES = [
  { key: "billed", label: t.billed, color: "#2A64A6" },
  { key: "collected", label: t.collected, color: "#B98A2E" },
] as const;

const pct = (v: number | null) => (v === null ? t.noData : `${v}%`);

export function Analytics() {
  const [months, setMonths] = useState<(typeof PERIODS)[number]>("6");
  const q = useOrgQuery<AnalyticsData>("/analytics/", { months });
  return (
    <>
      <PageHeader title={t.title} description={t.intro} />
      <Select
        containerClassName="mb-6 w-full max-w-xs"
        label={t.period}
        value={months}
        options={PERIODS.map((p) => ({ value: p, label: t.periods[p] }))}
        onChange={(e) => setMonths(e.target.value as (typeof PERIODS)[number])}
      />
      {q.isLoading ? <LoadingBlock /> : null}
      <QueryState
        data={q.data}
        isLoading={false}
        error={q.error}
        refetch={q.refetch}
      >
        {(data) => <View data={data} />}
      </QueryState>
    </>
  );
}

function View({ data }: { data: AnalyticsData }) {
  const n = data.now;
  const ccy = data.currency;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label={t.occupancy}
          value={pct(n.occupancy_rate)}
          detail={fmt(t.occupancyValue, {
            occupied: n.occupied,
            units: n.units,
          })}
        />
        <StatCard
          label={t.arrears}
          value={formatMoney(n.arrears, ccy)}
          tone={Number(n.arrears) > 0 ? "danger" : "default"}
          detail={fmt(t.arrearsDetail, { count: n.tenants_in_arrears })}
        />
        <StatCard
          label={t.repairs}
          value={n.repairs_open}
          detail={
            n.repair_median_days_90d === null
              ? fmt(t.repairsNoMedian, { count: n.repairs_reported_30d })
              : fmt(t.repairsDetail, { days: n.repair_median_days_90d })
          }
        />
        <StatCard
          label={t.leads}
          value={n.leads_30d}
          detail={fmt(t.leadsDetail, {
            won: n.leads_won_30d,
            viewings: n.viewings_30d,
          })}
        />
        <StatCard
          label={t.alerts}
          value={n.alerts_30d}
          detail={fmt(t.alertsDetail, { count: n.false_alarms_30d })}
        />
      </div>
      <Card title={t.chartTitle}>
        <p className="mb-3 text-sm text-ink-600">{t.chartHint}</p>
        <Legend />
        <ColumnChart rows={data.months} currency={ccy} />
      </Card>
      <DataTable
        caption={t.table}
        rows={data.months}
        rowKey={(r) => r.month}
        columns={[
          {
            key: "m",
            header: t.month,
            cell: (r) => formatMonth(r.month.slice(0, 7)),
          },
          {
            key: "b",
            header: t.billed,
            cell: (r) => formatMoney(r.billed, ccy),
          },
          {
            key: "c",
            header: t.collected,
            cell: (r) => formatMoney(r.collected, ccy),
          },
          {
            key: "r",
            header: t.collectionRate,
            cell: (r) => pct(r.collection_rate),
          },
          {
            key: "o",
            header: t.onTime,
            cell: (r) =>
              `${pct(r.on_time_rate)} (${r.paid_on_time}/${r.charges})`,
          },
          {
            key: "d",
            header: t.dues,
            cell: (r) =>
              Number(r.dues_billed) > 0
                ? formatMoney(r.dues_collected, ccy)
                : t.noData,
          },
        ]}
      />
    </div>
  );
}

function Legend() {
  return (
    <ul
      className="mb-2 flex flex-wrap gap-4 text-sm text-ink-700"
      aria-label={t.chartTitle}
    >
      {SERIES.map((s) => (
        <li key={s.key} className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: s.color }}
          />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

/** Rounded tick: 0, 1.2K, 3M… (axis only; exact values are in the tooltip and the table). */
function compact(v: number): string {
  if (v >= 1_000_000) return `${+(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${+(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= v) ?? v;
}

/** Grouped columns on one money axis: thin bars, 4px rounded tops, a 2px gap, hover/focus tooltip. */
function ColumnChart({
  rows,
  currency,
}: {
  rows: AnalyticsMonth[];
  currency: string;
}) {
  const [hover, setHover] = useState<{
    x: number;
    y: number;
    text: string;
  } | null>(null);
  const W = 640;
  const H = 240;
  const pad = { l: 48, r: 8, t: 12, b: 28 };
  const max = niceMax(
    Math.max(
      0,
      ...rows.flatMap((r) => [Number(r.billed), Number(r.collected)]),
    ),
  );
  const band = (W - pad.l - pad.r) / Math.max(rows.length, 1);
  const bar = Math.min(24, (band - 16) / 2);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max];

  return (
    // Below ~560px the chart keeps its size and scrolls inside the card, so axis text stays readable.
    <div className="overflow-x-auto">
      <div
        className="relative min-w-[560px]"
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label={`${t.chartTitle}. ${t.table}`}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line
                x1={pad.l}
                x2={W - pad.r}
                y1={y(v)}
                y2={y(v)}
                stroke="#DCE3EC"
                strokeWidth={1}
              />
              <text
                x={pad.l - 6}
                y={y(v) + 4}
                textAnchor="end"
                fontSize={11}
                fill="#5F6B7A"
              >
                {compact(v)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const cx = pad.l + band * i + band / 2;
            return (
              <g key={r.month}>
                {SERIES.map((s, j) => {
                  const v = Number(r[s.key]);
                  const top = y(v);
                  const h = Math.max(0, H - pad.b - top);
                  const x = cx - bar - 1 + j * (bar + 2); // 2px surface gap between the pair
                  const text = fmt(t.tooltip, {
                    month: formatMonth(r.month.slice(0, 7)),
                    series: s.label,
                    amount: formatMoney(r[s.key], currency),
                  });
                  const r4 = Math.min(4, h, bar / 2);
                  return (
                    <path
                      key={s.key}
                      d={`M${x},${H - pad.b} V${top + r4} Q${x},${top} ${x + r4},${top} H${x + bar - r4} Q${x + bar},${top} ${x + bar},${top + r4} V${H - pad.b} Z`}
                      fill={s.color}
                      tabIndex={0}
                      role="graphics-symbol"
                      aria-label={text}
                      className="cursor-default outline-none focus:opacity-80"
                      onMouseEnter={() =>
                        setHover({ x: x + bar / 2, y: top, text })
                      }
                      onFocus={() => setHover({ x: x + bar / 2, y: top, text })}
                      onBlur={() => setHover(null)}
                    />
                  );
                })}
                <text
                  x={cx}
                  y={H - 8}
                  textAnchor="middle"
                  fontSize={11}
                  fill="#5F6B7A"
                >
                  {formatMonth(r.month.slice(0, 7)).split(" ")[0]}
                </text>
              </g>
            );
          })}
        </svg>
        {hover && (
          <div
            role="tooltip"
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-md bg-ink-900 px-2 py-1 text-xs text-white shadow"
            style={{
              left: `${(hover.x / W) * 100}%`,
              top: `${(hover.y / H) * 100}%`,
            }}
          >
            {hover.text}
          </div>
        )}
      </div>
    </div>
  );
}
