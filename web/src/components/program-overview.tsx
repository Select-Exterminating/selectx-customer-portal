"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";

import { DataTable, DataTableFrame } from "@/components/data-table";
import { StoreLink } from "@/components/dashboard-link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { errorMessage } from "@/lib/api/errors";
import {
  useDashboardGetProgramDashboard,
  useDashboardGetRiskAssessmentDashboard,
} from "@/lib/api/generated/dashboard/dashboard";
import type { LabelCount, ProgramDashboard, StoreWatchRow } from "@/lib/api/generated/model";
import { RiskMap } from "@/components/risk-map";
import { StatTile } from "@/components/stat-tile";
import { cn } from "@/lib/utils";

const integer = new Intl.NumberFormat();
const percent = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 0 });

export function pct(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : percent.format(value);
}

export function num(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : integer.format(Math.round(value));
}

/** API dates are calendar dates (YYYY-MM-DD); show them without a timezone shift. */
export function day(value: string | null | undefined) {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatMonth(month: string) {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

export const BAND_COLOR: Record<string, string> = {
  Critical: "var(--risk-critical)",
  High: "var(--risk-high)",
  Elevated: "var(--risk-elevated)",
  Controlled: "var(--risk-controlled)",
  "No Service Data": "var(--border)",
};
export const BAND_CHIP: Record<string, string> = {
  Critical: "bg-risk-critical text-risk-critical-foreground",
  High: "bg-risk-high text-risk-high-foreground",
  Elevated: "bg-risk-elevated text-risk-elevated-foreground",
  Controlled: "bg-risk-controlled text-risk-controlled-foreground",
};
export const ACTIVITY_COLOR = [
  "var(--risk-controlled)",
  "var(--risk-elevated)",
  "var(--risk-high)",
  "var(--risk-critical)",
];
const ACTIVITY_LABEL = ["None", "Low", "Moderate", "Heavy"];
const ATTENTION_BADGE = {
  Escalated: { variant: "destructive", label: "Escalated" },
  Watch: { variant: "warning", label: "Watch" },
  Stable: { variant: "success", label: "Holding baseline" },
  "Not Yet Serviced": { variant: "outline", label: "Not yet serviced" },
} as const;

/** The dark band that opens a dashboard tab. */
export const STATEMENT_BAND =
  "relative overflow-hidden rounded-xl bg-[radial-gradient(120%_140%_at_100%_0%,var(--ink-glow)_0%,var(--ink)_60%)] px-6 py-8 text-white sm:px-8";

/** An uppercase label above a section. */
export function Eyebrow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p className={cn("text-xs font-bold tracking-[0.14em] text-primary uppercase", className)}>
      {children}
    </p>
  );
}

/** The opening statement band: how many stores came in active and how fast they stabilized. */
function ResultsBand({ d }: { d: ProgramDashboard }) {
  const r = d.results;
  const drop =
    r.early_rate !== null && r.late_rate !== null && r.early_rate > 0
      ? (r.late_rate - r.early_rate) / r.early_rate
      : null;
  const tiles: [string, string, string, string][] = [
    [num(r.median_days), "days", "Median days to Stabilized", "from first service"],
    [num(r.median_services), "services", "Median services to Stabilized", "service visits needed"],
    [
      pct(r.stabilized_share),
      "",
      "Stores brought to Stabilized",
      `${integer.format(r.stabilized)} of ${integer.format(r.intake_active)} stores with active rodents`,
    ],
    [
      drop === null ? "—" : `${drop > 0 ? "+" : "−"}${percent.format(Math.abs(drop))}`,
      "",
      "Change in rodent activity",
      `${pct(r.early_rate)} of visits in weeks 1–2 → ${pct(r.late_rate)} after day 90`,
    ],
    [pct(r.clean_after), "", "Clean visits after stabilizing", "median store, they stay clean"],
  ];
  return (
    <section className={STATEMENT_BAND}>
      <Eyebrow className="text-brand-green">
        Program results · every store measured from its first service
      </Eyebrow>
      <h2 className="mt-3 max-w-4xl text-2xl leading-snug sm:text-3xl">
        <span className="text-highlight">{integer.format(r.intake_active)} stores</span> came to
        Select with active rodents.{" "}
        <span className="text-highlight">{integer.format(r.stabilized)} reached Stabilized</span>
        {r.median_days !== null && (
          <>
            {" "}
            in a median of <span className="text-highlight">{num(r.median_days)} days</span>
          </>
        )}
        .
      </h2>
      <p className="mt-3 max-w-3xl text-sm text-ink-muted">
        Stores started on different dates, so every store is lined up on its own day one. Stabilized
        means 28+ days since the last rodent activity, with every visit since clean.
      </p>
      <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {tiles.map(([value, unit, label, note]) => (
          <div
            key={label}
            className="flex flex-col rounded-lg border border-t-[3px] border-white/10 border-t-brand-green bg-white/5 px-4 py-3.5"
          >
            <dt className="order-2 mt-2 text-xs font-bold">{label}</dt>
            <dd className="order-1 text-[40px] leading-none font-bold tabular-nums">
              {value}
              {unit && <span className="ml-1 text-lg font-bold text-ink-muted">{unit}</span>}
            </dd>
            <dd className="order-3 mt-1 text-xs text-ink-muted">{note}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The last rated visits as a line of dots: higher and warmer means more activity. */
function Spark({ scores }: { scores: number[] }) {
  if (scores.length === 0) return <span className="text-muted-foreground">—</span>;
  const x = (i: number) => 4 + i * 7;
  const y = (score: number) => 18 - score * 5;
  return (
    <svg
      width={x(scores.length - 1) + 5}
      height={22}
      role="img"
      aria-label={`Last ${scores.length} rated visits: ${scores.map((s) => ACTIVITY_LABEL[s]).join(", ")}`}
    >
      <polyline
        points={scores.map((s, i) => `${x(i)},${y(s)}`).join(" ")}
        fill="none"
        stroke="var(--chart-5)"
        strokeWidth={1.2}
      />
      {scores.map((s, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(s)}
          r={i === scores.length - 1 ? 3 : 2}
          fill={ACTIVITY_COLOR[s]}
        />
      ))}
    </svg>
  );
}

const WATCH_FILTERS = [
  [
    "Escalated",
    "Escalated",
    "Recurrence after stabilization, repeat zones, or a client-reported finding",
    "destructive",
  ],
  [
    "Watch",
    "Watch",
    "Recent activity, rising trend, open exclusion or sanitation items",
    "warning",
  ],
  ["Stable", "Holding baseline", "No flags in recent reports", "success"],
  ["regress", "Recurrences", "Stabilized, then activity again in the last 45 days", "destructive"],
  [
    "client",
    "Client-reported findings",
    "Food safety, EcoLab or store-team findings open and logged in the last 60 days",
    "destructive",
  ],
] as const;
const WATCH_TILE = {
  destructive: {
    value: "text-destructive",
    tile: "border-t-risk-critical",
    on: "bg-destructive-muted",
  },
  warning: { value: "text-warning-foreground", tile: "border-t-risk-elevated", on: "bg-warning" },
  success: { value: "text-success", tile: "border-t-risk-controlled", on: "bg-success-muted" },
} as const;

/** Which stores need attention now, from each store's own reports. */
const FLAG_RULES = [
  [
    "Client-reported finding",
    "A finding the customer's own people reported, open and logged in the last 60 days. Always escalates.",
  ],
  [
    "Recurrence after stabilization",
    "Reached Stabilized, then activity was found again within the last 45 days.",
  ],
  [
    "Active at last visit",
    "The latest rated visit, within 45 days, found activity. Moderate or heavy weighs more.",
  ],
  ["Repeat activity in same zone", "The same zone on three or more visits in the last 90 days."],
  [
    "Not yet stabilized",
    "60+ days since first service, activity in the last 60 days, and never Stabilized.",
  ],
  [
    "Rising activity trend",
    "Share of visits with activity in the last 30 days is 25+ points above the 60 days before.",
  ],
  ["Exclusion compromised", "The latest exclusion check, within 60 days, recorded it compromised."],
  [
    "Open structural backlog / recurring sanitation",
    "Five or more open structural items, or sanitation concerns on three of the last five visits.",
  ],
  [
    "Attention levels",
    "Escalated: recurrence with heavy or repeat activity, or flag weight of 7+. Watch: weight of 2+. Stable: no meaningful flags.",
  ],
] as const;

function StoreWatch({ d }: { d: ProgramDashboard }) {
  const [filter, setFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [flag, setFlag] = useState("");
  const [tier, setTier] = useState("");
  const [all, setAll] = useState(false);
  const counts = Object.fromEntries(d.portfolio.attention.map((a) => [a.label, a.stores]));
  const flags = useMemo(
    () => [
      ...new Map(d.stores.flatMap((s) => s.flags).map((f) => [f.code, f.label] as const)).entries(),
    ],
    [d.stores],
  );
  const tiers = useMemo(
    () => [...new Set(d.stores.flatMap((s) => (s.tier ? [s.tier] : [])))].sort(),
    [d.stores],
  );
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return d.stores.filter(
      (s) =>
        (!filter || s.attention === filter || s.flags.some((f) => f.code === filter)) &&
        (!flag || s.flags.some((f) => f.code === flag)) &&
        (!tier || s.tier === tier) &&
        (!q || [s.store_number, s.name, s.city].some((v) => (v ?? "").toLowerCase().includes(q))),
    );
  }, [d.stores, filter, flag, tier, query]);
  const shown = all ? rows : rows.slice(0, 15);
  return (
    <Card>
      <CardHeader>
        <Eyebrow>Store watch · every store measured against its own baseline</Eyebrow>
        <CardTitle className="text-xl">Which Stores Need Attention Now</CardTitle>
        <CardDescription>
          The program restores a store to its operational baseline. Store Watch flags any store that
          isn&apos;t holding it: recurrence after stabilization, activity at the last visit, repeat
          activity in one zone, rising activity, compromised exclusion, open structural backlog, or
          recurring sanitation concerns.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {WATCH_FILTERS.map(([key, label, note, tone]) => {
            const value =
              key === "regress"
                ? d.portfolio.recurrences
                : key === "client"
                  ? d.stores.filter((s) => s.flags.some((f) => f.code === "client")).length
                  : (counts[key] ?? 0);
            const active = filter === key;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(active ? "" : key)}
                className={cn(
                  "rounded-lg border border-t-[3px] border-border p-3 text-left transition-shadow hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  WATCH_TILE[tone].tile,
                  active && WATCH_TILE[tone].on,
                )}
              >
                <span
                  className={cn(
                    "block text-3xl leading-none font-bold tabular-nums",
                    WATCH_TILE[tone].value,
                  )}
                >
                  {integer.format(value)}
                </span>
                <span className="mt-1 block text-[13px] font-bold">{label}</span>
                <span className="block text-xs text-muted-foreground">{note}</span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-56 flex-col gap-1">
            <Label htmlFor="watch-find">Find a store</Label>
            <Input
              id="watch-find"
              type="search"
              placeholder="Store number, name, or city"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="watch-flag">Flag</Label>
            <NativeSelect id="watch-flag" value={flag} onChange={(e) => setFlag(e.target.value)}>
              <NativeSelectOption value="">All flags</NativeSelectOption>
              {flags.map(([code, label]) => (
                <NativeSelectOption key={code} value={code}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="watch-tier">RAMP tier</Label>
            <NativeSelect id="watch-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
              <NativeSelectOption value="">All tiers</NativeSelectOption>
              {tiers.map((t) => (
                <NativeSelectOption key={t} value={t}>
                  {t}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <p className="ml-auto text-sm text-muted-foreground">
            {integer.format(rows.length)} of {integer.format(d.stores.length)} stores
          </p>
        </div>
        <DataTableFrame>
          <DataTable>
            <thead>
              <tr>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Attention</th>
                <th className="p-3 font-medium">Why flagged</th>
                <th className="p-3 font-medium">Tier</th>
                <th className="p-3 text-right font-medium">Risk index</th>
                <th className="p-3 font-medium">Activity</th>
                <th className="p-3 font-medium">Last activity</th>
                <th className="p-3 font-medium">Last service</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((s) => (
                <WatchRow key={s.location_id} s={s} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-4 text-muted-foreground">
                    No stores match.
                  </td>
                </tr>
              )}
            </tbody>
          </DataTable>
        </DataTableFrame>
        {rows.length > 15 && (
          <Button variant="outline" className="self-center" onClick={() => setAll(!all)}>
            {all ? "Show fewer" : `Show all ${integer.format(rows.length)} stores`}
          </Button>
        )}
        <details className="text-sm">
          <summary className="cursor-pointer text-primary hover:underline">
            How stores are flagged
          </summary>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2">
            {FLAG_RULES.map(([name, rule]) => (
              <div key={name}>
                <dt className="font-bold">{name}</dt>
                <dd className="text-muted-foreground">{rule}</dd>
              </div>
            ))}
          </dl>
        </details>
      </CardContent>
    </Card>
  );
}

function WatchRow({ s }: { s: StoreWatchRow }) {
  const badge = ATTENTION_BADGE[s.attention as keyof typeof ATTENTION_BADGE];
  return (
    <tr className="align-top">
      <td className="p-3">
        <StoreLink locationId={s.location_id} className="text-sm font-bold">
          {s.store_number ? `#${s.store_number}` : s.name}
        </StoreLink>
        <span className="block text-xs text-muted-foreground">
          {[s.store_number ? s.name : null, s.city, s.state].filter(Boolean).join(" · ")}
        </span>
      </td>
      <td className="p-3">
        {badge ? (
          <Badge variant={badge.variant}>
            <span aria-hidden className="size-1.5 rounded-full bg-current" />
            {badge.label}
          </Badge>
        ) : (
          s.attention
        )}
      </td>
      <td className="p-3">
        <span className="flex flex-wrap gap-1">
          {s.flags.length === 0 && <span className="text-muted-foreground">No flags</span>}
          {s.flags.map((f) => (
            <Badge
              key={f.code}
              variant={f.weight >= 3 ? "destructive" : f.weight === 2 ? "warning" : "pending"}
              title={f.detail}
            >
              {f.short}
            </Badge>
          ))}
        </span>
      </td>
      <td className="p-3">{s.tier ?? "—"}</td>
      <td className="p-3 text-right">
        <span
          className={cn(
            "inline-block min-w-[2.1em] rounded px-1.5 py-0.5 text-center font-bold",
            BAND_CHIP[s.risk_band],
          )}
        >
          {s.risk_index ?? "—"}
          <span className="sr-only"> {s.risk_band}</span>
        </span>
      </td>
      <td className="p-3">
        <Spark scores={s.spark} />
      </td>
      <td className="p-3 whitespace-nowrap">
        {day(s.last_activity)}
        {s.days_since_activity !== null && (
          <span className="block text-xs text-muted-foreground">
            {integer.format(s.days_since_activity)} days ago
          </span>
        )}
      </td>
      <td className="p-3 whitespace-nowrap">{day(s.last_service)}</td>
    </tr>
  );
}

/** A chart card: title, description, chart, and its data as a table. */
export function ChartCard({
  title,
  description,
  rows,
  children,
}: {
  title: string;
  description: string;
  rows: [string, string][];
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {children}
        <details className="text-sm">
          <summary className="cursor-pointer text-primary hover:underline">Show table</summary>
          <DataTable className="mt-2 max-w-sm">
            <caption className="sr-only">{title}</caption>
            <tbody>
              {rows.map(([label, value]) => (
                <tr key={label} className="border-b border-border last:border-0">
                  <th scope="row" className="py-1 text-left font-normal">
                    {label}
                  </th>
                  <td className="py-1 text-right tabular-nums">{value}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </details>
      </CardContent>
    </Card>
  );
}

const curveConfig = {
  activity_rate: { label: "Visits with activity", color: "var(--chart-1)" },
  heavy_rate: { label: "Heavy activity", color: "var(--destructive)" },
} satisfies ChartConfig;

function ActivityCurve({ d }: { d: ProgramDashboard }) {
  return (
    <ChartCard
      title="Rodent Activity From Day One"
      description="Share of rated visits finding rodent activity, by two-week period since each store's first visit."
      rows={d.curve.map((c) => [c.label, `${pct(c.activity_rate)} of ${integer.format(c.rated)}`])}
    >
      <ChartContainer config={curveConfig} className="aspect-auto h-64 w-full">
        <LineChart data={d.curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={40}
            tickFormatter={(v: number) => percent.format(v)}
          />
          <ChartTooltip
            content={<ChartTooltipContent formatter={(v) => percent.format(Number(v))} />}
          />
          <Line dataKey="activity_rate" stroke="var(--color-activity_rate)" strokeWidth={2} />
          <Line
            dataKey="heavy_rate"
            stroke="var(--color-heavy_rate)"
            strokeWidth={2}
            strokeDasharray="4 3"
          />
        </LineChart>
      </ChartContainer>
    </ChartCard>
  );
}

function EarlyVsLate({ d }: { d: ProgramDashboard }) {
  const r = d.results;
  const pairs: [string, number | null, number | null, string][] = [
    [
      "Visits with activity",
      r.early_rate,
      r.late_rate,
      `${integer.format(r.early_visits)} vs. ${integer.format(r.late_visits)} visits`,
    ],
    ["Heavy activity", r.early_heavy, r.late_heavy, "share of rated visits"],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>First Two Weeks vs. Day 90 Onward</CardTitle>
        <CardDescription>
          Visits finding rodent activity early in the program and later.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {pairs.map(([label, early, late, note]) => (
          <div key={label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div className="rounded-lg border border-border p-3 text-center">
              <span className="block text-2xl font-bold">{pct(early)}</span>
              <span className="block text-xs text-muted-foreground">First two weeks</span>
            </div>
            <span aria-hidden className="text-muted-foreground">
              →
            </span>
            <div className="rounded-lg border border-primary bg-muted p-3 text-center">
              <span className="block text-2xl font-bold text-primary">{pct(late)}</span>
              <span className="block text-xs text-muted-foreground">Day 90 onward</span>
            </div>
            <span className="col-span-3 text-sm">
              <strong>{label}</strong> · {note}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

const storesConfig = { stores: { label: "Stores", color: "var(--chart-1)" } } satisfies ChartConfig;

function Buckets({
  title,
  description,
  data,
  median,
}: {
  title: string;
  description: string;
  data: LabelCount[];
  median?: string;
}) {
  return (
    <ChartCard
      title={title}
      description={description}
      rows={data.map((b) => [b.label, integer.format(b.stores)])}
    >
      {median && (
        <p className="text-sm">
          <span className="text-2xl font-bold text-primary">{median}</span>
        </p>
      )}
      <ChartContainer config={storesConfig} className="aspect-auto h-56 w-full">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} interval={0} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
          <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
          <Bar dataKey="stores" fill="var(--color-stores)" />
        </BarChart>
      </ChartContainer>
    </ChartCard>
  );
}

function PortfolioMap({ d }: { d: ProgramDashboard }) {
  const rated = d.stores.filter((s) => s.risk_index !== null);
  return (
    <ChartCard
      title="Portfolio Risk Map"
      description="Each store, colored by its RAMP risk index. Click a dot to open the store."
      rows={[...rated]
        .sort((a, b) => (b.risk_index ?? 0) - (a.risk_index ?? 0))
        .slice(0, 10)
        .map((s) => [
          s.store_number ? `#${s.store_number} · ${s.city ?? ""}` : (s.name ?? ""),
          `${s.risk_index} · ${s.risk_band}`,
        ])}
    >
      <RiskMap stores={d.stores} bandColor={BAND_COLOR} />
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {d.portfolio.bands.map((b) => (
          <li key={b.label} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{ background: BAND_COLOR[b.label] }}
            />
            {b.label} · {integer.format(b.stores)}
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}

function RiskBands({ d }: { d: ProgramDashboard }) {
  return (
    <ChartCard
      title="Stores by Risk Band"
      description="Current RAMP risk index: rodent activity (40), open structural vulnerabilities (25), sanitation (20), and secondary pests (15) over the 90 days to each store's latest rated visit."
      rows={d.portfolio.bands.map((b) => [b.label, integer.format(b.stores)])}
    >
      <ChartContainer config={storesConfig} className="aspect-auto h-56 w-full">
        <BarChart
          data={d.portfolio.bands}
          layout="vertical"
          margin={{ top: 0, right: 16, left: 8, bottom: 0 }}
        >
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} width={110} />
          <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
          <Bar dataKey="stores">
            {d.portfolio.bands.map((b) => (
              <Cell key={b.label} fill={BAND_COLOR[b.label] ?? "var(--border)"} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
    </ChartCard>
  );
}

const monthlyConfig = {
  services: { label: "Services", color: "var(--chart-3)" },
  activity_rate: { label: "Visits with activity", color: "var(--chart-1)" },
} satisfies ChartConfig;

function Monthly({ d }: { d: ProgramDashboard }) {
  return (
    <ChartCard
      title="Services and Rodent Activity by Month"
      description="Service visits per month (bars) and the share of rated visits that found activity (line)."
      rows={d.monthly.map((m) => [
        formatMonth(m.month),
        `${integer.format(m.services)} services · ${pct(m.activity_rate)}`,
      ])}
    >
      <ChartContainer config={monthlyConfig} className="aspect-auto h-64 w-full">
        <ComposedChart data={d.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="month"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            tickFormatter={formatMonth}
          />
          <YAxis
            yAxisId="services"
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            width={36}
          />
          <YAxis
            yAxisId="rate"
            orientation="right"
            tickLine={false}
            axisLine={false}
            width={40}
            tickFormatter={(v: number) => percent.format(v)}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={(m) => formatMonth(String(m))}
                formatter={(v, name) =>
                  name === "activity_rate" ? percent.format(Number(v)) : integer.format(Number(v))
                }
              />
            }
          />
          <Bar yAxisId="services" dataKey="services" fill="var(--color-services)" />
          <Line
            yAxisId="rate"
            dataKey="activity_rate"
            stroke="var(--color-activity_rate)"
            strokeWidth={2}
            connectNulls
          />
        </ComposedChart>
      </ChartContainer>
    </ChartCard>
  );
}

function PortfolioToday({ d }: { d: ProgramDashboard }) {
  const p = d.portfolio;
  const change = p.rodent_free_change;
  const tiles: [string, string, string][] = [
    [
      "Stores in program",
      integer.format(p.stores_serviced),
      `${integer.format(p.stores)} locations`,
    ],
    [
      "Services performed",
      integer.format(p.services),
      `plus ${integer.format(p.inspections)} inspections`,
    ],
    [
      "Rodent-free visits · last 30 days",
      pct(p.rodent_free_30d),
      change === null
        ? `${integer.format(p.rated_30d)} rated visits`
        : `${change >= 0 ? "+" : "−"}${Math.abs(Math.round(change * 100))} pts vs. prior 30 days`,
    ],
    ["Rodents removed (documented)", integer.format(p.captures), "captures stated in reports"],
    [
      "Structural vulnerabilities remediated",
      pct(p.remediation_rate),
      `${integer.format(p.structural_remediated)} of ${integer.format(p.structural_logged)} logged`,
    ],
    [
      "Stores with activity at last visit",
      integer.format(p.stores_active_now),
      "latest rated visit",
    ],
  ];
  return (
    <section className="flex flex-col gap-3">
      <Eyebrow>Portfolio status today</Eyebrow>
      <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {tiles.map(([label, value, note]) => (
          <StatTile key={label} label={label} value={value} note={note} />
        ))}
      </dl>
    </section>
  );
}

export function AssessmentCoverage({
  companyId,
  billToId,
  state,
}: {
  companyId: string;
  billToId: string;
  state: string;
}) {
  const assessments = useDashboardGetRiskAssessmentDashboard(companyId, {
    ...(billToId ? { bill_to_id: billToId } : {}),
    ...(state ? { state } : {}),
  });
  if (assessments.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {errorMessage(assessments.error, "Could not load the risk assessment coverage.")}
        </AlertDescription>
      </Alert>
    );
  }
  const data = (assessments.data?.data.coverage ?? []).map((c) => ({
    state: c.state,
    assessed: c.assessed,
    remaining: Math.max(0, (c.target ?? c.in_program) - c.assessed),
  }));
  return (
    <ChartCard
      title="Risk Assessment Coverage"
      description="Restaurants with a risk assessment, against the state's target or every location there."
      rows={data.map((c) => [c.state, `${c.assessed} of ${c.assessed + c.remaining}`])}
    >
      <ChartContainer config={coverageConfig} className="aspect-auto h-64 w-full">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="state" tickLine={false} axisLine={false} tickMargin={8} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={36} />
          <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
          <Bar dataKey="assessed" stackId="a" fill="var(--color-assessed)" />
          <Bar dataKey="remaining" stackId="a" fill="var(--color-remaining)" />
        </BarChart>
      </ChartContainer>
    </ChartCard>
  );
}

const coverageConfig = {
  assessed: { label: "Assessed", color: "var(--chart-1)" },
  remaining: { label: "Remaining", color: "var(--muted)" },
} satisfies ChartConfig;

/** The program overview, in the RAMP portal's layout. */
export function ProgramOverview({
  companyId,
  billToId,
  state,
}: {
  companyId: string;
  billToId: string;
  state: string;
}) {
  const program = useDashboardGetProgramDashboard(companyId, {
    ...(billToId ? { bill_to_id: billToId } : {}),
    ...(state ? { state } : {}),
  });

  if (program.isPending) return <p className="text-muted-foreground">Loading program results…</p>;
  if (program.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {errorMessage(program.error, "Could not load the program results.")}
        </AlertDescription>
      </Alert>
    );
  }
  const d = program.data.data;
  const r = d.results;
  return (
    <div className="flex flex-col gap-6">
      <ResultsBand d={d} />
      <StoreWatch d={d} />
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <ActivityCurve d={d} />
        <EarlyVsLate d={d} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Buckets
          title="Time to Stabilized"
          description="Stores that came in with activity and reached Stabilized, by time from first service."
          data={r.time_to_stabilized}
        />
        <Buckets
          title="Services per RAMP"
          description="Service visits per store since its program started."
          data={r.services_per_ramp}
          median={
            r.services_per_store === null
              ? undefined
              : `${num(r.services_per_store)} median services`
          }
        />
      </div>
      <PortfolioToday d={d} />
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <PortfolioMap d={d} />
        <RiskBands d={d} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Monthly d={d} />
        <AssessmentCoverage companyId={companyId} billToId={billToId} state={state} />
      </div>
    </div>
  );
}
