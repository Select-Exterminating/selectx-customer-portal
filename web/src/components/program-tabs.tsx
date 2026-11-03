"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";

import {
  BAND_COLOR,
  ChartCard,
  day,
  Eyebrow,
  formatMonth,
  num,
  pct,
  STATEMENT_BAND,
} from "@/components/program-overview";
import { DataTable, DataTableFrame } from "@/components/data-table";
import { DashboardLink } from "@/components/dashboard-link";
import { StatTile } from "@/components/stat-tile";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
  useDashboardGetProgramTabs,
} from "@/lib/api/generated/dashboard/dashboard";
import type {
  Breakdown,
  ProgramDashboard,
  ProgramTabs,
  RodentActivityTab,
  SanitationTab,
  StoreWatchRow,
  StructuralTab,
  TrackerRow,
} from "@/lib/api/generated/model";

const integer = new Intl.NumberFormat();
const percent = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 0 });
const axisPercent = (v: number) => percent.format(v);

type Scope = { companyId: string; billToId: string; state: string };

function params({ billToId, state }: Scope) {
  return { ...(billToId ? { bill_to_id: billToId } : {}), ...(state ? { state } : {}) };
}

function useTabs(scope: Scope) {
  return useDashboardGetProgramTabs(scope.companyId, params(scope));
}

/** Loads the shared tab data and shows its loading and error states. */
function WithTabs({
  scope,
  render,
}: {
  scope: Scope;
  render: (d: ProgramTabs) => React.ReactNode;
}) {
  const tabs = useTabs(scope);
  if (tabs.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (tabs.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(tabs.error, "Could not load this tab.")}</AlertDescription>
      </Alert>
    );
  }
  return <>{render(tabs.data.data)}</>;
}

function StoreLink({
  s,
}: {
  s: {
    location_id: string;
    store_number: string | null;
    name: string | null;
    city: string | null;
    state: string | null;
  };
}) {
  return (
    <>
      <DashboardLink href={`/locations/${s.location_id}`} className="font-medium">
        {s.store_number ? `#${s.store_number}` : s.name}
      </DashboardLink>
      <span className="block text-xs text-muted-foreground">
        {[s.store_number ? s.name : null, s.city, s.state].filter(Boolean).join(" · ")}
      </span>
    </>
  );
}

function TableCard({
  title,
  description,
  toolbar,
  children,
}: {
  title: string;
  description: string;
  toolbar?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {toolbar}
        <DataTableFrame className="max-h-[32rem]">{children}</DataTableFrame>
      </CardContent>
    </Card>
  );
}

const mentionsConfig = {
  mentions: { label: "Logged", color: "var(--chart-1)" },
  remediated: { label: "Remediated", color: "var(--chart-3)" },
} satisfies ChartConfig;

/** Horizontal bars of findings by category or zone. `stacked` splits off the remediated part. */
function BreakdownChart({
  title,
  description,
  data,
  remediated,
}: {
  title: string;
  description: string;
  data: Breakdown[];
  remediated?: boolean;
}) {
  const rows = data.slice(0, 12).map((b) => ({
    label: b.label,
    remediated: b.remediated,
    mentions: remediated ? b.mentions - b.remediated : b.mentions,
    total: b.mentions,
    stores: b.stores,
  }));
  return (
    <ChartCard
      title={title}
      description={description}
      rows={data.map((b) => [
        b.label,
        `${integer.format(b.mentions)} · ${integer.format(b.stores)} stores${
          remediated ? ` · ${integer.format(b.remediated)} remediated` : ""
        }`,
      ])}
    >
      <ChartContainer
        config={mentionsConfig}
        className="aspect-auto w-full"
        style={{ height: Math.max(180, rows.length * 30 + 24) }}
      >
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="label"
            tickLine={false}
            axisLine={false}
            width={150}
            interval={0}
          />
          <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
          {remediated && <Bar dataKey="remediated" stackId="a" fill="var(--color-remediated)" />}
          <Bar dataKey="mentions" stackId="a" fill="var(--color-mentions)" />
        </BarChart>
      </ChartContainer>
    </ChartCard>
  );
}

function ChartGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-6 lg:grid-cols-2">{children}</div>;
}

// --- Rodent activity ---------------------------------------------------------------------------

const rateConfig = {
  activity_rate: { label: "Any activity", color: "var(--chart-1)" },
  heavy_rate: { label: "Heavy activity", color: "var(--destructive)" },
} satisfies ChartConfig;
const capturesConfig = {
  captures: { label: "Captures", color: "var(--chart-1)" },
} satisfies ChartConfig;

function RodentActivity({ a }: { a: RodentActivityTab }) {
  return (
    <div className="flex flex-col gap-6">
      <ChartGrid>
        <ChartCard
          title="Activity Falls as Stores Move Through the Program"
          description="Share of rated visits finding rodent activity, by month since each store's first visit."
          rows={a.cohort.map((c) => [
            `Month ${c.month}`,
            `${pct(c.activity_rate)} of ${integer.format(c.rated)} · ${integer.format(c.stores)} stores`,
          ])}
        >
          <ChartContainer config={rateConfig} className="aspect-auto h-64 w-full">
            <LineChart data={a.cohort} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={(m: number) => `M${m}`}
              />
              <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={axisPercent} />
              <ChartTooltip
                content={<ChartTooltipContent formatter={(v) => percent.format(Number(v))} />}
              />
              <Line dataKey="activity_rate" stroke="var(--color-activity_rate)" strokeWidth={2} />
            </LineChart>
          </ChartContainer>
        </ChartCard>
        <ChartCard
          title="Activity Rate by Calendar Month"
          description="Any activity and heavy activity, as a share of rated visits."
          rows={a.months.map((m) => [
            formatMonth(m.month),
            `${pct(m.activity_rate)} any · ${pct(m.heavy_rate)} heavy`,
          ])}
        >
          <ChartContainer config={rateConfig} className="aspect-auto h-64 w-full">
            <LineChart data={a.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={formatMonth}
              />
              <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={axisPercent} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(m) => formatMonth(String(m))}
                    formatter={(v) => percent.format(Number(v))}
                  />
                }
              />
              <Line
                dataKey="activity_rate"
                stroke="var(--color-activity_rate)"
                strokeWidth={2}
                connectNulls
              />
              <Line
                dataKey="heavy_rate"
                stroke="var(--color-heavy_rate)"
                strokeWidth={2}
                strokeDasharray="4 3"
                connectNulls
              />
            </LineChart>
          </ChartContainer>
        </ChartCard>
        <ChartCard
          title="Documented Captures by Month"
          description="Rodents removed where the notes state a number. Notes that only say captures aren't counted."
          rows={a.months.map((m) => [formatMonth(m.month), integer.format(m.captures)])}
        >
          <ChartContainer config={capturesConfig} className="aspect-auto h-64 w-full">
            <BarChart data={a.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={formatMonth}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={36} />
              <ChartTooltip
                content={<ChartTooltipContent labelFormatter={(m) => formatMonth(String(m))} />}
              />
              <Bar dataKey="captures" fill="var(--color-captures)" />
            </BarChart>
          </ChartContainer>
        </ChartCard>
        <BreakdownChart
          title="Where Rodent Activity Was Found"
          description="Visits with activity, by zone of the restaurant."
          data={a.zones}
        />
      </ChartGrid>
      <TableCard
        title="Stores With Recent Activity"
        description="Stores whose latest rated visit found activity, most recent first."
      >
        <DataTable>
          <thead>
            <tr>
              <th className="p-3 font-medium">Store</th>
              <th className="p-3 font-medium">Last activity</th>
              <th className="p-3 font-medium">Level</th>
              <th className="p-3 font-medium">Zones</th>
              <th className="p-3 text-right font-medium">Risk index</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {a.recent.map((s) => (
              <tr key={s.location_id} className="align-top">
                <td className="p-3">
                  <StoreLink s={s} />
                </td>
                <td className="p-3 whitespace-nowrap">{day(s.last_activity)}</td>
                <td className="p-3 capitalize">{s.level}</td>
                <td className="p-3">{s.zones.join(", ") || "—"}</td>
                <td className="p-3 text-right tabular-nums">
                  {s.risk_index ?? "—"} · {s.risk_band}
                </td>
              </tr>
            ))}
            {a.recent.length === 0 && (
              <tr>
                <td colSpan={5} className="p-4 text-muted-foreground">
                  No stores with activity at their latest visit.
                </td>
              </tr>
            )}
          </tbody>
        </DataTable>
      </TableCard>
    </div>
  );
}

// --- Structural --------------------------------------------------------------------------------

const structuralMonthConfig = {
  logged: { label: "Logged", color: "var(--chart-3)" },
  rate: { label: "Remediated", color: "var(--chart-1)" },
} satisfies ChartConfig;

function Structural({ s }: { s: StructuralTab }) {
  const [query, setQuery] = useState("");
  const open = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? s.open.filter((o) =>
          [o.store_number, o.name, o.zone, o.category, o.where, o.issue].some((v) =>
            (v ?? "").toLowerCase().includes(q),
          ),
        )
      : s.open;
  }, [s.open, query]);
  const months = s.months.map((m) => ({
    ...m,
    rate: m.logged ? m.remediated / m.logged : null,
  }));
  return (
    <div className="flex flex-col gap-6">
      <ChartGrid>
        <BreakdownChart
          title="Structural Findings by Type"
          description="Findings logged across all visits; the darker part is logged as remediated."
          data={s.categories}
          remediated
        />
        <BreakdownChart
          title="Structural Findings by Zone"
          description="Where entry points and voids were found."
          data={s.zones}
          remediated
        />
      </ChartGrid>
      <ChartCard
        title="Findings Logged vs. Remediated by Month"
        description="Bars: structural findings logged. Line: share of those logged as remediated."
        rows={months.map((m) => [
          formatMonth(m.month),
          `${integer.format(m.logged)} logged · ${pct(m.rate)} remediated`,
        ])}
      >
        <ChartContainer config={structuralMonthConfig} className="aspect-auto h-64 w-full">
          <ComposedChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={formatMonth}
            />
            <YAxis yAxisId="n" allowDecimals={false} tickLine={false} axisLine={false} width={36} />
            <YAxis
              yAxisId="rate"
              orientation="right"
              domain={[0, 1]}
              tickLine={false}
              axisLine={false}
              width={40}
              tickFormatter={axisPercent}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(m) => formatMonth(String(m))}
                  formatter={(v, name) =>
                    name === "rate" ? percent.format(Number(v)) : integer.format(Number(v))
                  }
                />
              }
            />
            <Bar yAxisId="n" dataKey="logged" fill="var(--color-logged)" />
            <Line
              yAxisId="rate"
              dataKey="rate"
              stroke="var(--color-rate)"
              strokeWidth={2}
              connectNulls
            />
          </ComposedChart>
        </ChartContainer>
      </ChartCard>
      <TableCard
        title="Open Structural Vulnerabilities"
        description="The latest report of each store's distinct vulnerability (type and zone) where it was still open or in progress."
        toolbar={
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-56 flex-col gap-1">
              <Label htmlFor="structural-find">Find</Label>
              <Input
                id="structural-find"
                type="search"
                placeholder="Store, zone, or issue"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="ml-auto text-sm text-muted-foreground">
              {integer.format(open.length)} of {integer.format(s.open.length)} open
            </p>
          </div>
        }
      >
        <DataTable>
          <thead>
            <tr>
              <th className="p-3 font-medium">Store</th>
              <th className="p-3 font-medium">Type</th>
              <th className="p-3 font-medium">Zone</th>
              <th className="p-3 font-medium">Issue</th>
              <th className="p-3 font-medium">Status</th>
              <th className="p-3 font-medium">Last reported</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {open.slice(0, 200).map((o, i) => (
              <tr key={`${o.location_id}-${o.category}-${o.zone}-${i}`} className="align-top">
                <td className="p-3">
                  <StoreLink s={o} />
                </td>
                <td className="p-3">{o.category}</td>
                <td className="p-3">{o.zone}</td>
                <td className="p-3">
                  {o.issue ?? "—"}
                  {o.where && (
                    <span className="block text-xs text-muted-foreground">{o.where}</span>
                  )}
                </td>
                <td className="p-3">
                  <Badge variant={o.status === "in_progress" ? "pending" : "warning"}>
                    {o.status === "in_progress" ? "In progress" : "Open"}
                  </Badge>
                </td>
                <td className="p-3 whitespace-nowrap">{day(o.last_reported)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </TableCard>
    </div>
  );
}

// --- Sanitation & pests ------------------------------------------------------------------------

const concernConfig = {
  sanitation_share: { label: "Sanitation concern", color: "var(--chart-1)" },
  pest_share: { label: "Secondary pests", color: "var(--chart-5)" },
} satisfies ChartConfig;

function Sanitation({ s }: { s: SanitationTab }) {
  return (
    <div className="flex flex-col gap-6">
      <ChartGrid>
        <BreakdownChart
          title="Sanitation Concerns by Type"
          description="Conditions that feed or shelter pests, as logged by technicians."
          data={s.categories}
        />
        <BreakdownChart
          title="Sanitation Concerns by Zone"
          description="Where in the restaurant they were found."
          data={s.zones}
        />
        <BreakdownChart
          title="Secondary Pests Found"
          description="Non-rodent pests noted during visits."
          data={s.pests}
        />
        <ChartCard
          title="Share of Visits With Concerns by Month"
          description="Visits with any sanitation concern, and with secondary pests."
          rows={s.months.map((m) => [
            formatMonth(m.month),
            `${pct(m.sanitation_share)} sanitation · ${pct(m.pest_share)} pests`,
          ])}
        >
          <ChartContainer config={concernConfig} className="aspect-auto h-64 w-full">
            <LineChart data={s.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={formatMonth}
              />
              <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={axisPercent} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(m) => formatMonth(String(m))}
                    formatter={(v) => percent.format(Number(v))}
                  />
                }
              />
              <Line
                dataKey="sanitation_share"
                stroke="var(--color-sanitation_share)"
                strokeWidth={2}
                connectNulls
              />
              <Line
                dataKey="pest_share"
                stroke="var(--color-pest_share)"
                strokeWidth={2}
                connectNulls
              />
            </LineChart>
          </ChartContainer>
        </ChartCard>
      </ChartGrid>
      <TableCard
        title="Stores With Recurring Sanitation Concerns"
        description="Stores with sanitation findings on three or more visits."
      >
        <DataTable>
          <thead>
            <tr>
              <th className="p-3 font-medium">Store</th>
              <th className="p-3 text-right font-medium">Visits with concerns</th>
              <th className="p-3 text-right font-medium">Of all visits</th>
              <th className="p-3 font-medium">Most logged</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {s.stores.map((r) => (
              <tr key={r.location_id} className="align-top">
                <td className="p-3">
                  <StoreLink s={r} />
                </td>
                <td className="p-3 text-right tabular-nums">
                  {integer.format(r.visits_with_concerns)} of {integer.format(r.visits)}
                </td>
                <td className="p-3 text-right tabular-nums">{pct(r.share)}</td>
                <td className="p-3">{r.top_category ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </TableCard>
    </div>
  );
}

// --- Tracker -----------------------------------------------------------------------------------

function Tracker({ rows }: { rows: TrackerRow[] }) {
  const [query, setQuery] = useState("");
  const [tier, setTier] = useState("");
  const tiers = useMemo(
    () => [...new Set(rows.flatMap((r) => (r.tier ? [r.tier] : [])))].sort(),
    [rows],
  );
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!tier || r.tier === tier) &&
        (!q || [r.store_number, r.name, r.city].some((v) => (v ?? "").toLowerCase().includes(q))),
    );
  }, [rows, query, tier]);
  return (
    <div className="flex flex-col gap-4">
      <Alert>
        <AlertDescription>
          These milestones come from completed service visits. Launch, inspection requested,
          proposal submitted, and approved aren&apos;t tracked here yet, and each store&apos;s stage
          is based on its service history.
        </AlertDescription>
      </Alert>
      <TableCard
        title="Program Tracker"
        description="Every store with a RAMP order and where it stands, newest first."
        toolbar={
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-56 flex-col gap-1">
              <Label htmlFor="tracker-find">Find a store</Label>
              <Input
                id="tracker-find"
                type="search"
                placeholder="Store number, name, or city"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="tracker-tier">RAMP tier</Label>
              <NativeSelect
                id="tracker-tier"
                value={tier}
                onChange={(e) => setTier(e.target.value)}
              >
                <NativeSelectOption value="">All tiers</NativeSelectOption>
                {tiers.map((t) => (
                  <NativeSelectOption key={t} value={t}>
                    {t}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <p className="ml-auto text-sm text-muted-foreground">
              {integer.format(shown.length)} of {integer.format(rows.length)} stores
            </p>
          </div>
        }
      >
        <DataTable className="min-w-[820px]">
          <thead>
            <tr>
              <th className="p-3 font-medium">Store</th>
              <th className="p-3 font-medium">Tier</th>
              <th className="p-3 font-medium">Stage</th>
              <th className="p-3 font-medium">First inspection</th>
              <th className="p-3 font-medium">First service</th>
              <th className="p-3 font-medium">First monitoring</th>
              <th className="p-3 font-medium">First stabilized</th>
              <th className="p-3 font-medium">Last service</th>
              <th className="p-3 text-right font-medium">Services</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {shown.map((r) => (
              <tr key={r.location_id} className="align-top">
                <td className="p-3">
                  <StoreLink s={r} />
                </td>
                <td className="p-3 whitespace-nowrap">{r.tier ?? "—"}</td>
                <td className="p-3">{r.stage}</td>
                <td className="p-3 whitespace-nowrap">{day(r.first_inspection)}</td>
                <td className="p-3 whitespace-nowrap">{day(r.first_service)}</td>
                <td className="p-3 whitespace-nowrap">{day(r.first_monitoring)}</td>
                <td className="p-3 whitespace-nowrap">{day(r.first_stabilized)}</td>
                <td className="p-3 whitespace-nowrap">{day(r.last_service)}</td>
                <td className="p-3 text-right tabular-nums">{integer.format(r.services)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </TableCard>
    </div>
  );
}

// --- Stores and the risk model: from the program dashboard --------------------------------------

function WithProgram({
  scope,
  render,
}: {
  scope: Scope;
  render: (d: ProgramDashboard) => React.ReactNode;
}) {
  const program = useDashboardGetProgramDashboard(scope.companyId, params(scope));
  if (program.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (program.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {errorMessage(program.error, "Could not load this tab.")}
        </AlertDescription>
      </Alert>
    );
  }
  return <>{render(program.data.data)}</>;
}

const SCORE_COLUMNS: {
  key: string;
  label: string;
  numeric?: boolean;
  value: (s: StoreWatchRow) => string | number;
}[] = [
  { key: "store", label: "Store", value: (s) => Number(s.store_number ?? 0) },
  { key: "tier", label: "Tier", value: (s) => s.tier ?? "" },
  { key: "services", label: "Services", numeric: true, value: (s) => s.services },
  { key: "risk", label: "Risk index", numeric: true, value: (s) => s.risk_index ?? -1 },
  { key: "open", label: "Open structural", numeric: true, value: (s) => s.structural_open },
  {
    key: "days",
    label: "Days to Stabilized",
    numeric: true,
    value: (s) => s.days_to_stabilized ?? -1,
  },
  { key: "last_activity", label: "Last activity", value: (s) => s.last_activity ?? "" },
  { key: "last_service", label: "Last service", value: (s) => s.last_service ?? "" },
];

function bandStyle(s: StoreWatchRow) {
  return { background: BAND_COLOR[s.risk_band] ?? "var(--border)" };
}

function StoreScorecard({ d }: { d: ProgramDashboard }) {
  const [query, setQuery] = useState("");
  const [band, setBand] = useState("");
  const [sort, setSort] = useState({ key: "services", desc: true });
  const [all, setAll] = useState(false);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const column = SCORE_COLUMNS.find((c) => c.key === sort.key) ?? SCORE_COLUMNS[0];
    return d.stores
      .filter(
        (s) =>
          (!band || s.risk_band === band) &&
          (!q || [s.store_number, s.name, s.city].some((v) => (v ?? "").toLowerCase().includes(q))),
      )
      .sort((a, b) => {
        const x = column.value(a);
        const y = column.value(b);
        const order = x < y ? -1 : x > y ? 1 : 0;
        return sort.desc ? -order : order;
      });
  }, [d.stores, query, band, sort]);
  const top = useMemo(
    () => [...d.stores].sort((a, b) => b.services - a.services).filter((s) => s.services > 0),
    [d.stores],
  );
  const bars = all ? top : top.slice(0, 25);
  const most = Math.max(1, ...bars.map((s) => s.services));
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Services Performed per Store</CardTitle>
          <CardDescription>
            Every service visit on file, colored by the store&apos;s current risk band.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ul className="flex flex-col gap-1">
            {bars.map((s) => (
              <li
                key={s.location_id}
                className="grid grid-cols-[6rem_1fr_3rem] items-center gap-2 text-sm"
              >
                <DashboardLink href={`/locations/${s.location_id}`}>
                  {s.store_number ? `#${s.store_number}` : s.name}
                </DashboardLink>
                <span
                  aria-hidden
                  className="h-3"
                  style={{ ...bandStyle(s), width: `${(s.services / most) * 100}%` }}
                />
                <span className="text-right tabular-nums">{integer.format(s.services)}</span>
              </li>
            ))}
          </ul>
          {top.length > 25 && (
            <button
              type="button"
              className="self-start text-sm text-primary hover:underline"
              onClick={() => setAll(!all)}
            >
              {all ? "Show fewer" : `Show all ${integer.format(top.length)} stores`}
            </button>
          )}
        </CardContent>
      </Card>
      <TableCard
        title="Store Scorecard"
        description="Sort by any column. Open a store for its full history."
        toolbar={
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-56 flex-col gap-1">
              <Label htmlFor="score-find">Find a store</Label>
              <Input
                id="score-find"
                type="search"
                placeholder="Store number, name, or city"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="score-band">Risk band</Label>
              <NativeSelect id="score-band" value={band} onChange={(e) => setBand(e.target.value)}>
                <NativeSelectOption value="">All risk bands</NativeSelectOption>
                {d.portfolio.bands.map((b) => (
                  <NativeSelectOption key={b.label} value={b.label}>
                    {b.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <p className="ml-auto text-sm text-muted-foreground">
              {integer.format(rows.length)} of {integer.format(d.stores.length)} stores
            </p>
          </div>
        }
      >
        <DataTable className="min-w-[820px]">
          <thead>
            <tr>
              {SCORE_COLUMNS.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={sort.key === c.key ? (sort.desc ? "descending" : "ascending") : "none"}
                  className={c.numeric ? "p-3 text-right font-medium" : "p-3 font-medium"}
                >
                  <button
                    type="button"
                    className="hover:text-foreground"
                    onClick={() =>
                      setSort({
                        key: c.key,
                        desc: sort.key === c.key ? !sort.desc : Boolean(c.numeric),
                      })
                    }
                  >
                    {c.label}
                    {sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((s) => (
              <tr key={s.location_id} className="align-top">
                <td className="p-3">
                  <StoreLink s={s} />
                </td>
                <td className="p-3 whitespace-nowrap">{s.tier ?? "—"}</td>
                <td className="p-3 text-right tabular-nums">{integer.format(s.services)}</td>
                <td className="p-3 text-right whitespace-nowrap tabular-nums">
                  <span aria-hidden className="mr-2 inline-block size-2.5" style={bandStyle(s)} />
                  {s.risk_index ?? "—"}
                  <span className="sr-only"> {s.risk_band}</span>
                </td>
                <td className="p-3 text-right tabular-nums">{s.structural_open}</td>
                <td className="p-3 text-right tabular-nums">{s.days_to_stabilized ?? "—"}</td>
                <td className="p-3 whitespace-nowrap">{day(s.last_activity)}</td>
                <td className="p-3 whitespace-nowrap">{day(s.last_service)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      </TableCard>
    </div>
  );
}

function RiskModel({ d }: { d: ProgramDashboard }) {
  const rated = useMemo(
    () =>
      d.stores
        .filter((s) => s.risk_index !== null)
        .sort((a, b) => (b.risk_index ?? 0) - (a.risk_index ?? 0))
        .slice(0, 25),
    [d.stores],
  );
  return (
    <div className="flex flex-col gap-6">
      <Alert>
        <AlertDescription>
          This company&apos;s own risk scores and priority lists (service tickets, closures, outside
          inspection findings, risk ratings) haven&apos;t been loaded, so they can&apos;t be
          compared with field findings yet.
        </AlertDescription>
      </Alert>
      <ChartGrid>
        <Card>
          <CardHeader>
            <CardTitle>How the RAMP Risk Index Works</CardTitle>
            <CardDescription>
              Each store gets a 0–100 score from its own visits over the 90 days ending at its
              latest rated visit. Higher means more exposure.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              {[
                [
                  "Rodent activity · up to 40",
                  "Average activity level on rated visits (none 0, low 1, moderate 2, heavy 3), as a share of heavy.",
                ],
                [
                  "Open structural vulnerabilities · up to 25",
                  "Distinct vulnerabilities (type and zone) whose latest report, within the 90 days, still lists them as open. Six or more scores the full 25.",
                ],
                ["Sanitation · up to 20", "Share of visits that logged a sanitation concern."],
                [
                  "Secondary pests · up to 15",
                  "Share of visits that found cockroaches, flies, or other pests.",
                ],
                ["Bands", "Critical 55+ · High 35–54 · Elevated 20–34 · Controlled under 20."],
              ].map(([name, rule]) => (
                <div key={name}>
                  <dt className="font-bold">{name}</dt>
                  <dd className="text-muted-foreground">{rule}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
        <TableCard
          title="Highest Risk Index"
          description="The 25 stores scoring highest from field findings."
        >
          <DataTable>
            <thead>
              <tr>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Band</th>
                <th className="p-3 text-right font-medium">Index</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rated.map((s) => (
                <tr key={s.location_id} className="align-top">
                  <td className="p-3">
                    <StoreLink s={s} />
                  </td>
                  <td className="p-3">
                    <span aria-hidden className="mr-2 inline-block size-2.5" style={bandStyle(s)} />
                    {s.risk_band}
                  </td>
                  <td className="p-3 text-right tabular-nums">{s.risk_index}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </TableCard>
      </ChartGrid>
    </div>
  );
}

// --- Executive review --------------------------------------------------------------------------

const programMonthConfig = {
  visits: { label: "Visits", color: "var(--chart-1)" },
} satisfies ChartConfig;

function Tile({ value, label, note }: { value: string; label: string; note?: string }) {
  return <StatTile label={label} value={value} note={note} />;
}

function HealthTable({
  title,
  rows,
}: {
  title: string;
  rows: ProgramTabs["executive"]["by_state"];
}) {
  return (
    <TableCard
      title={title}
      description="Treated stores by their outcome today; recurrence counts stores that lost Stabilized at least once."
    >
      <DataTable>
        <thead>
          <tr>
            <th className="p-3 font-medium">{title.split(" by ")[1]}</th>
            <th className="p-3 text-right font-medium">Treated</th>
            <th className="p-3 text-right font-medium">Stabilized</th>
            <th className="p-3 text-right font-medium">Share</th>
            <th className="p-3 text-right font-medium">With a recurrence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((r) => (
            <tr key={r.label}>
              <td className="p-3">{r.label}</td>
              <td className="p-3 text-right tabular-nums">{integer.format(r.treated)}</td>
              <td className="p-3 text-right tabular-nums">{integer.format(r.stabilized)}</td>
              <td className="p-3 text-right tabular-nums">
                {pct(r.treated ? r.stabilized / r.treated : null)}
              </td>
              <td className="p-3 text-right tabular-nums">{integer.format(r.recurrence)}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </TableCard>
  );
}

function Executive({ d }: { d: ProgramTabs }) {
  const e = d.executive;
  const reduction =
    e.risk_start && e.risk_now !== null ? (e.risk_start - e.risk_now) / e.risk_start : null;
  const tiers = e.tiers.map((t) => `${integer.format(t.visits)} ${t.label}`).join(" · ");
  return (
    <div className="flex flex-col gap-8">
      <section className={STATEMENT_BAND}>
        <Eyebrow className="text-brand-green">
          Executive review · live from the field record
        </Eyebrow>
        <h2 className="mt-3 max-w-4xl text-2xl leading-snug sm:text-3xl">
          <span className="text-highlight">{integer.format(e.stores_serviced)} stores</span> served
          since {day(e.inception)},{" "}
          <span className="text-highlight">{integer.format(e.stabilized_now)} stabilized</span>{" "}
          today.
        </h2>
        <p className="mt-3 max-w-3xl text-sm text-ink-muted">
          Every figure here is calculated from completed service visits and their findings, through{" "}
          {day(e.through)}.
        </p>
      </section>

      <section className="flex flex-col gap-4">
        <Eyebrow>Section 01 · Investment and progress</Eyebrow>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            value={integer.format(e.stores_serviced)}
            label="Stores serviced"
            note={tiers || undefined}
          />
          <Tile value={integer.format(e.service_visits)} label="Service visits" />
          <Tile
            value={integer.format(e.captures)}
            label="Rodent captures"
            note="stated in the notes"
          />
          <Tile
            value={integer.format(e.visit_types.reduce((t, v) => t + v.visits, 0))}
            label="Visits of every type"
          />
        </dl>
        <ChartGrid>
          <BreakdownChart
            title="Visits by Type"
            description="Distinct visits by the kind of order."
            data={e.visit_types.map((v) => ({
              label: v.label,
              mentions: v.visits,
              stores: 0,
              remediated: 0,
            }))}
          />
          <ChartCard
            title="Visits by Month"
            description="A location's completed orders on one date count as one visit."
            rows={e.months.map((m) => [formatMonth(m.month), integer.format(m.visits)])}
          >
            <ChartContainer config={programMonthConfig} className="aspect-auto h-64 w-full">
              <BarChart data={e.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis
                  dataKey="month"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={formatMonth}
                />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={36} />
                <ChartTooltip
                  content={<ChartTooltipContent labelFormatter={(m) => formatMonth(String(m))} />}
                />
                <Bar dataKey="visits" fill="var(--color-visits)" />
              </BarChart>
            </ChartContainer>
          </ChartCard>
        </ChartGrid>
      </section>

      <section className="flex flex-col gap-4">
        <Eyebrow>Section 02 · Portfolio health today</Eyebrow>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            value={pct(e.treated ? e.stabilized_now / e.treated : null)}
            label="Stabilized"
            note={`${integer.format(e.stabilized_now)} of ${integer.format(e.treated)} treated stores`}
          />
          <Tile
            value={pct(e.treated ? e.active_now / e.treated : null)}
            label="Active stabilization"
            note={`${integer.format(e.active_now)} under active management`}
          />
          <Tile
            value={pct(reduction)}
            label="Risk reduction"
            note={`Mean risk index ${num(e.risk_start)} → ${num(e.risk_now)}`}
          />
          <Tile
            value={integer.format(e.recurrence)}
            label="With a recurrence"
            note="lost Stabilized at least once"
          />
        </dl>
        <ChartGrid>
          <HealthTable title="Outcomes by State" rows={e.by_state} />
          <HealthTable title="Outcomes by Tier" rows={e.by_tier} />
        </ChartGrid>
      </section>

      <section className="flex flex-col gap-4">
        <Eyebrow>Section 03 · The yield</Eyebrow>
        <ChartGrid>
          <TableCard
            title="RAMP Phase vs. Monitoring Phase"
            description="Rated orders by their service code: activity concentrates in active intervention."
          >
            <DataTable>
              <thead>
                <tr>
                  <th className="p-3 font-medium">Phase</th>
                  <th className="p-3 text-right font-medium">Rated orders</th>
                  <th className="p-3 text-right font-medium">With activity</th>
                  <th className="p-3 text-right font-medium">Heavy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {e.phases.map((p) => (
                  <tr key={p.phase}>
                    <td className="p-3">{p.phase}</td>
                    <td className="p-3 text-right tabular-nums">{integer.format(p.rated)}</td>
                    <td className="p-3 text-right tabular-nums">{pct(p.activity_rate)}</td>
                    <td className="p-3 text-right tabular-nums">{pct(p.heavy_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </TableCard>
          <TableCard
            title="Rats and Mice"
            description="Stores whose findings name only one species, and how they stabilize."
          >
            <DataTable>
              <thead>
                <tr>
                  <th className="p-3 font-medium">Species</th>
                  <th className="p-3 text-right font-medium">Stores</th>
                  <th className="p-3 text-right font-medium">Stabilized now</th>
                  <th className="p-3 text-right font-medium">Median days</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {d.activity.species.map((s) => (
                  <tr key={s.species}>
                    <td className="p-3">{s.species}</td>
                    <td className="p-3 text-right tabular-nums">{integer.format(s.stores)}</td>
                    <td className="p-3 text-right tabular-nums">{integer.format(s.stabilized)}</td>
                    <td className="p-3 text-right tabular-nums">{num(s.median_days)}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </TableCard>
        </ChartGrid>
      </section>

      <section className="flex flex-col gap-4">
        <Eyebrow>Section 04 · The operating model</Eyebrow>
        <BreakdownChart
          title="Risk-Based Monitoring"
          description="The condition sets the cadence: each treated store, placed by its own record."
          data={e.cadence.map((v) => ({
            label: v.label,
            mentions: v.visits,
            stores: v.visits,
            remediated: 0,
          }))}
        />
      </section>
    </div>
  );
}

export function RodentActivityTabView({ scope }: { scope: Scope }) {
  return <WithTabs scope={scope} render={(d) => <RodentActivity a={d.activity} />} />;
}
export function StructuralTabView({ scope }: { scope: Scope }) {
  return <WithTabs scope={scope} render={(d) => <Structural s={d.structural} />} />;
}
export function SanitationTabView({ scope }: { scope: Scope }) {
  return <WithTabs scope={scope} render={(d) => <Sanitation s={d.sanitation} />} />;
}
export function TrackerTabView({ scope }: { scope: Scope }) {
  return <WithTabs scope={scope} render={(d) => <Tracker rows={d.tracker} />} />;
}
export function ExecutiveTabView({ scope }: { scope: Scope }) {
  return <WithTabs scope={scope} render={(d) => <Executive d={d} />} />;
}
export function StoreScorecardTabView({ scope }: { scope: Scope }) {
  return <WithProgram scope={scope} render={(d) => <StoreScorecard d={d} />} />;
}
export function RiskModelTabView({ scope }: { scope: Scope }) {
  return <WithProgram scope={scope} render={(d) => <RiskModel d={d} />} />;
}
