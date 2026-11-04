"use client";

import Link from "next/link";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { useContext, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, XAxis, YAxis } from "recharts";

import { DashboardLink, DashboardLinksContext, useStoreParam } from "@/components/dashboard-link";
import { DataTable, DataTableFrame } from "@/components/data-table";
import {
  ACTIVITY_COLOR,
  BAND_CHIP,
  BAND_COLOR,
  ChartCard,
  day,
  Eyebrow,
  num,
  pct,
} from "@/components/program-overview";
import { StatTile } from "@/components/stat-tile";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import {
  Dialog,
  DialogClose,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "@/components/ui/dialog";
import { errorMessage } from "@/lib/api/errors";
import { useDashboardGetStoreProfile } from "@/lib/api/generated/dashboard/dashboard";
import type {
  ProfileAssessment,
  ProfileFinding,
  ProfileVisit,
  StoreProfile,
  TrendPoint,
} from "@/lib/api/generated/model";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

const ATTENTION = {
  Escalated: { variant: "destructive", label: "Escalated", tint: "bg-destructive-muted" },
  Watch: { variant: "warning", label: "Watch", tint: "bg-warning" },
  Stable: { variant: "success", label: "Holding baseline", tint: "bg-success-muted" },
  "Not Yet Serviced": { variant: "outline", label: "Not yet serviced", tint: "bg-card" },
} as const;
const LEVELS = ["none", "low", "moderate", "heavy"];
const LEVEL_LABEL: Record<string, string> = {
  none: "None",
  low: "Low",
  moderate: "Moderate",
  heavy: "Heavy",
};

function level(value: string | null | undefined) {
  return value ? (LEVEL_LABEL[value] ?? value) : "Not stated";
}

function levelColor(value: string | null | undefined) {
  const i = LEVELS.indexOf(value ?? "");
  return i >= 0 ? ACTIVITY_COLOR[i] : "var(--chart-5)";
}

/** "mass_trapping" to "Mass trapping". */
function visitType(value: string | null | undefined) {
  if (!value) return "Service";
  const words = value.replaceAll("_", " ");
  return words[0].toUpperCase() + words.slice(1);
}

function fullDay(value: string | null | undefined) {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { dateStyle: "medium" });
}

function daysAgo(days: number) {
  return days === 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

function ActivityDot({ value }: { value: string | null | undefined }) {
  return (
    <span
      aria-hidden
      className="inline-block size-2 shrink-0 rounded-full"
      style={{ background: levelColor(value) }}
    />
  );
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {note && <CardDescription>{note}</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">{children}</CardContent>
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

function Why({ p }: { p: StoreProfile }) {
  const attention = ATTENTION[p.attention as keyof typeof ATTENTION] ?? ATTENTION.Stable;
  const j = p.journey;
  let body: React.ReactNode;
  if (p.flags.length > 0) {
    body = (
      <ul className="flex flex-col gap-2">
        {p.flags.map((f) => (
          <li key={f.code} className="grid gap-1 sm:grid-cols-[7.5rem_1fr] sm:gap-2.5">
            <span>
              <Badge
                variant={f.weight >= 3 ? "destructive" : f.weight === 2 ? "warning" : "pending"}
              >
                {f.short}
              </Badge>
            </span>
            <span className="text-[13px]">
              <b>{f.label}.</b> {f.detail}
            </span>
          </li>
        ))}
      </ul>
    );
  } else if (p.attention === "Not Yet Serviced") {
    body = <p className="text-[13px]">No rated service visits are on file yet.</p>;
  } else {
    body = (
      <p className="text-[13px]">
        No flags in recent reports.{" "}
        {j.first_stabilized
          ? `Rodent-free since ${fullDay(j.first_stabilized)}.`
          : j.clean_from_start
            ? "No rodent activity found since the first visit."
            : ""}
      </p>
    );
  }
  const title =
    p.attention === "Escalated"
      ? "Why This Store Is Escalated"
      : p.flags.length > 0
        ? "What to Watch"
        : p.attention === "Not Yet Serviced"
          ? "Awaiting First Service"
          : "Holding at Baseline";
  return (
    <section className={cn("flex flex-col gap-2 rounded-lg border px-4 py-3.5", attention.tint)}>
      <h3 className="text-[15px]">{title}</h3>
      {body}
    </section>
  );
}

function JourneySide({
  eyebrow,
  index,
  band,
  rows,
  now,
}: {
  eyebrow: string;
  index: number | null;
  band: string;
  rows: ([string, string] | null)[];
  now?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border px-4 py-3.5",
        now ? "border-2 border-foreground bg-card" : "border-border bg-row",
      )}
    >
      <p className="text-[11px] font-bold tracking-[0.12em] text-muted-foreground uppercase">
        {eyebrow}
      </p>
      <span
        className={cn(
          "w-fit rounded-md px-2 py-1 text-4xl leading-none font-bold tabular-nums",
          BAND_CHIP[band],
        )}
      >
        {index ?? "—"}
      </span>
      <p className="mb-1.5 text-xs font-bold">Risk index · {band}</p>
      <dl className="flex flex-col text-xs">
        {rows.map(
          (row) =>
            row && (
              <div
                key={row[0]}
                className="grid grid-cols-[8.5rem_1fr] gap-2 border-t border-border py-1"
              >
                <dt className="text-muted-foreground">{row[0]}</dt>
                <dd className="font-bold">{row[1]}</dd>
              </div>
            ),
        )}
      </dl>
    </div>
  );
}

function Journey({ p }: { p: StoreProfile }) {
  const j = p.journey;
  const assessment = p.assessments.at(-1);
  const change = j.index_change;
  return (
    <Section title="Where It Started vs. Where It Is Now">
      <div className="grid items-stretch gap-3.5 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <JourneySide
          eyebrow="Start · first two rated weeks"
          index={j.start_index}
          band={j.start_band}
          rows={[
            ["First visit", fullDay(j.first_visit)],
            j.first_rated && j.first_rated !== j.first_visit
              ? ["First rated visit", fullDay(j.first_rated)]
              : null,
            ["Activity at intake", level(j.start_activity)],
            assessment
              ? [
                  "Risk assessment",
                  `${fullDay(assessment.day)}${assessment.max_zone ? ` · highest zone ${assessment.max_zone} of 5` : ""}`,
                ]
              : null,
            assessment?.recommendation ? ["Recommended", assessment.recommendation] : null,
          ]}
        />
        <div className="flex flex-col items-center justify-center gap-1 text-3xl font-bold text-primary">
          <span aria-hidden className="rotate-90 md:rotate-0">
            →
          </span>
          {change !== null && (
            <b className={cn("text-[13px]", change <= 0 ? "text-primary" : "text-destructive")}>
              {change > 0 ? "+" : change < 0 ? "−" : "±"}
              {Math.abs(change)} pts
            </b>
          )}
        </div>
        <JourneySide
          now
          eyebrow={`Now · ${fullDay(j.last_rated)}`}
          index={j.now_index}
          band={j.now_band}
          rows={[
            ["Latest visit", level(j.now_activity)],
            [
              "Outcome",
              j.outcome
                ? `${j.outcome}${j.stabilized_since ? ` since ${fullDay(j.stabilized_since)}` : ""}`
                : "Not yet measured",
            ],
            j.first_stabilized
              ? [
                  "First stabilized",
                  `${fullDay(j.first_stabilized)}${j.days_to_stabilized !== null ? ` · ${j.days_to_stabilized} days from first service` : ""}${j.recurrences ? ` · ${j.recurrences} ${j.recurrences === 1 ? "recurrence" : "recurrences"}` : ""}`,
                ]
              : null,
            j.cadence ? ["Recommended cadence", `${j.cadence} · ${j.cadence_why}`] : null,
            [
              "Last activity",
              j.last_activity
                ? `${fullDay(j.last_activity)}${j.days_since_activity !== null ? ` · ${daysAgo(j.days_since_activity)}` : ""}`
                : "None found",
            ],
            j.first_monitoring ? ["First monitoring order", fullDay(j.first_monitoring)] : null,
          ]}
        />
      </div>
    </Section>
  );
}

const BAND_ZONES: [number, number, string][] = [
  [0, 20, "Controlled"],
  [20, 35, "Elevated"],
  [35, 55, "High"],
  [55, 100, "Critical"],
];
const trendConfig = {
  index: { label: "Risk index", color: "var(--chart-3)" },
} satisfies ChartConfig;

function TrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: TrendPoint & { time: number } }[];
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="flex max-w-xs flex-col gap-1 rounded-lg border border-border bg-popover p-2.5 text-xs shadow-md">
      <b>
        {fullDay(point.day)} · {visitType(point.visit_type)}
      </b>
      <span>
        Risk index {point.index} · {point.band}
      </span>
      <span className="flex items-center gap-1.5">
        <ActivityDot value={point.activity} /> {level(point.activity)} activity
      </span>
      {point.summary && <span className="text-muted-foreground">{point.summary}</span>}
    </div>
  );
}

function Trend({ p }: { p: StoreProfile }) {
  const data = p.trend.map((t) => ({ ...t, time: new Date(`${t.day}T00:00:00`).getTime() }));
  const top = Math.max(60, ...p.trend.map((t) => t.index + 5));
  return (
    <ChartCard
      title="Risk Index Over Time"
      description="The risk index recalculated at every rated visit from the 90 days before it. Dots are colored by the rodent activity that visit found. Hover for the visit's summary."
      rows={p.trend.map((t) => [fullDay(t.day), `${t.index} · ${t.band} · ${level(t.activity)}`])}
    >
      {p.trend.length < 2 ? (
        <Empty>Not enough rated visits yet to draw a trend.</Empty>
      ) : (
        <>
          <ChartContainer config={trendConfig} className="aspect-auto h-56 w-full">
            <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              {BAND_ZONES.filter(([lo]) => lo < top).map(([lo, hi, band]) => (
                <ReferenceArea
                  key={band}
                  y1={lo}
                  y2={Math.min(hi, top)}
                  fill={BAND_COLOR[band]}
                  fillOpacity={0.07}
                  label={{ value: band, position: "insideTopRight", fontSize: 11 }}
                />
              ))}
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="time"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={(t: number) =>
                  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" })
                }
              />
              <YAxis domain={[0, top]} tickLine={false} axisLine={false} width={30} />
              <ChartTooltip content={<TrendTooltip />} />
              <Line
                dataKey="index"
                stroke="var(--color-index)"
                strokeWidth={2}
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; index?: number }) => (
                  <circle
                    key={props.index}
                    cx={props.cx}
                    cy={props.cy}
                    r={4}
                    stroke="var(--card)"
                    strokeWidth={1.4}
                    fill={levelColor(data[props.index ?? 0]?.activity)}
                  />
                )}
              />
            </LineChart>
          </ChartContainer>
          <ActivityLegend />
        </>
      )}
    </ChartCard>
  );
}

function ActivityLegend({ levels = ["heavy", "moderate", "low", "none"] }: { levels?: string[] }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {levels.map((l) => (
        <span key={l} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm" style={{ background: levelColor(l) }} />
          {level(l)}
        </span>
      ))}
    </div>
  );
}

function shortMonth(month: string, multiYear: boolean) {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    ...(multiYear ? { year: "2-digit" } : {}),
  });
}

function ActivityGrid({ p }: { p: StoreProfile }) {
  const { months, rated, zones } = p.activity_grid;
  const multiYear = months.length > 0 && months[0].slice(0, 4) !== months.at(-1)?.slice(0, 4);
  return (
    <Section
      title="Rodent Activity by Zone and Month"
      note="Where activity was found, month by month. A cell shows the heaviest activity that month. Repeat activity in one zone points to an entry point or harborage that needs re-exclusion."
    >
      {zones.length === 0 ? (
        <Empty>No rodent activity has been recorded in any zone.</Empty>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-[3px] text-[11px]">
              <thead>
                <tr>
                  <th scope="col" className="px-1 text-left font-bold text-muted-foreground">
                    Zone
                  </th>
                  {months.map((m) => (
                    <th
                      key={m}
                      scope="col"
                      className="px-1 text-center font-bold whitespace-nowrap text-muted-foreground"
                    >
                      {shortMonth(m, multiYear)}
                    </th>
                  ))}
                  <th scope="col" className="px-1 font-bold text-muted-foreground">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {zones.map((z) => (
                  <tr key={z.zone}>
                    <th scope="row" className="pr-2.5 text-left font-bold whitespace-nowrap">
                      {z.zone}
                    </th>
                    {z.levels.map((l, i) => (
                      <td
                        key={months[i]}
                        title={`${z.zone} · ${months[i]} · ${l ? level(LEVELS[l]) : "None"}`}
                        className="h-[22px] min-w-[22px] rounded bg-accent text-center"
                        style={l ? { background: ACTIVITY_COLOR[l] } : undefined}
                      >
                        <span className="sr-only">{l ? level(LEVELS[l]) : "None"}</span>
                      </td>
                    ))}
                    <td className="text-center font-bold tabular-nums">{z.total}</td>
                  </tr>
                ))}
                <tr className="text-muted-foreground">
                  <th scope="row" className="pr-2.5 text-left font-normal whitespace-nowrap">
                    Rated visits
                  </th>
                  {rated.map((n, i) => (
                    <td key={months[i]} className="text-center tabular-nums">
                      {n}
                    </td>
                  ))}
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
          <ActivityLegend levels={["low", "moderate", "heavy"]} />
        </>
      )}
    </Section>
  );
}

function RecentServices({ visits, canOpen }: { visits: ProfileVisit[]; canOpen: boolean }) {
  return (
    <Section title="Most Recent Services">
      {visits.length === 0 ? (
        <Empty>No services on file.</Empty>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {visits.slice(0, 6).map((v) => (
            <article
              key={v.day}
              className="flex flex-col gap-1 rounded-lg border border-l-4 border-border px-3 py-2.5"
              style={{ borderLeftColor: levelColor(v.activity) }}
            >
              <div className="flex items-center justify-between gap-2 text-[13px]">
                <b>{fullDay(v.day)}</b>
                <span className="inline-flex items-center gap-1.5 text-xs">
                  <ActivityDot value={v.activity} /> {level(v.activity)}
                </span>
              </div>
              <p className="text-[11px] font-bold text-muted-foreground">
                {[
                  visitType(v.visit_type),
                  ...v.technicians,
                  v.captures ? `${v.captures} captured` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {(v.zones.length > 0 || v.evidence.length > 0) && (
                <p className="text-[11px]">{[...v.zones, ...v.evidence].join(" · ")}</p>
              )}
              {v.summaries.map((s) => (
                <p key={s} className="text-xs leading-snug">
                  {s}
                </p>
              ))}
              {canOpen && v.report_id && (
                <Link
                  href={`/service-reports/${v.report_id}`}
                  className="text-xs text-primary hover:underline"
                >
                  Service report
                </Link>
              )}
            </article>
          ))}
        </div>
      )}
    </Section>
  );
}

function Score({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>;
  const band =
    value >= 4 ? "Critical" : value >= 3 ? "High" : value >= 2 ? "Elevated" : "Controlled";
  return (
    <span
      className={cn(
        "inline-block min-w-[1.6rem] rounded px-1 text-center font-bold",
        BAND_CHIP[band],
      )}
    >
      {value}
    </span>
  );
}

function Assessment({ a, open }: { a: ProfileAssessment; open: boolean }) {
  const linked = useContext(DashboardLinksContext);
  return (
    <details open={open} className="rounded-lg border border-border">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2.5 text-[13px]">
        <b>{fullDay(a.day)}</b>
        {a.classification && <Badge variant="outline">{a.classification}</Badge>}
        <span>Risk index {num(a.risk_index)}</span>
        {a.recommendation && <Badge variant="pending">Recommended: {a.recommendation}</Badge>}
        <span className="text-xs text-muted-foreground">
          {[
            a.inspector,
            `${a.rodent_zones} rodent ${a.rodent_zones === 1 ? "zone" : "zones"}`,
            `${a.pest_zones} pest ${a.pest_zones === 1 ? "zone" : "zones"}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </summary>
      <div className="flex flex-col gap-2 border-t border-border p-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span>
            Sanitation <b>{num(a.sanitation_index)}</b>
          </span>
          <span>
            Structural <b>{num(a.structural_index)}</b>
          </span>
          <span>
            Highest zone <b>{a.max_zone ?? "—"}</b>
          </span>
          {linked && (
            <DashboardLink href={`/risk-inspections/${a.inspection_id}`}>Full report</DashboardLink>
          )}
        </div>
        <DataTableFrame>
          <DataTable className="min-w-[44rem]">
            <thead>
              <tr>
                <th scope="col">Zone</th>
                <th scope="col">Sanitation</th>
                <th scope="col">Structural</th>
                <th scope="col">Overall</th>
                <th scope="col">Rodent</th>
                <th scope="col">Pest</th>
                <th scope="col">Inspector notes</th>
              </tr>
            </thead>
            <tbody>
              {a.zones.map((z) => (
                <tr key={z.zone} className="align-top">
                  <td>
                    <b>{z.zone}</b>
                    {z.areas.length > 0 && (
                      <span className="block text-muted-foreground">{z.areas.join(", ")}</span>
                    )}
                  </td>
                  <td>
                    <Score value={z.sanitation} />
                  </td>
                  <td>
                    <Score value={z.structural} />
                  </td>
                  <td>
                    <Score value={z.overall} />
                  </td>
                  <td>{z.rodent ? <Badge variant="destructive">Yes</Badge> : "No"}</td>
                  <td>
                    {z.pest ? (
                      <Badge variant="warning">{z.pest_types.join(", ") || "Yes"}</Badge>
                    ) : (
                      "No"
                    )}
                  </td>
                  <td>
                    {z.notes.map((n) => (
                      <p key={n}>{n}</p>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </DataTableFrame>
      </div>
    </details>
  );
}

function ProgramRecord({ p }: { p: StoreProfile }) {
  const j = p.journey;
  const facts: [string, string][] = [
    ["Risk index", p.journey.now_index === null ? "—" : String(p.journey.now_index)],
    ["Risk band", j.now_band],
    ["Services performed", num(p.numbers.services)],
    ["Inspections", num(p.numbers.inspections)],
    ["Documented captures", num(p.numbers.captures)],
    ["Activity rate", pct(p.numbers.activity_rate)],
    ["Last activity found", j.last_activity ? fullDay(j.last_activity) : "None found"],
    ["Open structural vulnerabilities", num(p.numbers.structural_open)],
    ["RAMP tier", p.tier ?? "—"],
    ["Stage (from service history)", p.stage],
    ["First monitoring order", fullDay(j.first_monitoring)],
    ["Team director", p.team_director ?? "—"],
    ["Executive team director", p.executive_team_director ?? "—"],
    ["Risk assessment recommendation", p.assessments[0]?.recommendation ?? "—"],
  ];
  return (
    <Section title="Program Record">
      <dl className="grid gap-x-3.5 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="flex min-w-0 flex-col gap-0.5">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="wrap-anywhere">{value}</dd>
          </div>
        ))}
      </dl>
      {p.risk_points && (
        <p className="text-xs text-muted-foreground">
          Index points: {p.risk_points.activity} rodent activity · {p.risk_points.structural} open
          structural · {p.risk_points.sanitation} sanitation · {p.risk_points.pests} secondary
          pests.
        </p>
      )}
    </Section>
  );
}

function Timeline({ visits }: { visits: ProfileVisit[] }) {
  const dated = visits.map((v) => ({ v, t: new Date(`${v.day}T00:00:00`).getTime() }));
  const times = dated.map((d) => d.t);
  const first = Math.min(...times);
  const span = Math.max(...times) - first || 1;
  const rows = ["heavy", "moderate", "low", "none", null];
  return (
    <Section
      title="Visit Timeline"
      note="Each mark is a visit, placed by the rodent activity it found. The service log below lists them."
    >
      {visits.length === 0 ? (
        <Empty>No visits on file.</Empty>
      ) : (
        <>
          <div aria-hidden className="relative h-24 rounded border border-border bg-row">
            {dated.map(({ v, t }) => (
              <span
                key={v.day}
                title={`${fullDay(v.day)} · ${visitType(v.visit_type)} · ${level(v.activity)}`}
                className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-card"
                style={{
                  left: `calc(${((t - first) / span) * 96 + 2}%)`,
                  top: `${(rows.indexOf(v.activity) + 0.5) * 20}%`,
                  background: levelColor(v.activity),
                }}
              />
            ))}
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{fullDay(dated.at(-1)?.v.day)}</span>
            <span>{fullDay(dated[0]?.v.day)}</span>
          </div>
          <ActivityLegend />
        </>
      )}
    </Section>
  );
}

function FindingTable({
  findings,
  status,
  empty,
}: {
  findings: ProfileFinding[];
  status: boolean;
  empty: string;
}) {
  if (findings.length === 0) return <Empty>{empty}</Empty>;
  return (
    <DataTableFrame className="max-h-80">
      <DataTable>
        <thead>
          <tr>
            <th scope="col">Reported</th>
            <th scope="col">Zone</th>
            <th scope="col">{status ? "Issue" : "Finding"}</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => (
            <tr key={`${f.day}-${f.category}-${i}`} className="align-top">
              <td className="whitespace-nowrap">{day(f.day)}</td>
              <td>{f.zone ?? "—"}</td>
              <td>
                <b>{f.category}</b>
                {!status && f.severity && ` · ${f.severity}`}
                {status && f.status === "in_progress" && " · in progress"}
                {(f.where || f.issue) && (
                  <span className="block text-muted-foreground">
                    {[f.where, f.issue].filter(Boolean).join(": ")}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </DataTableFrame>
  );
}

function ServiceLog({ visits, canOpen }: { visits: ProfileVisit[]; canOpen: boolean }) {
  return (
    <Section title="Service Log" note="Every visit on file for this store, newest first.">
      {visits.length === 0 ? (
        <Empty>No visits on file.</Empty>
      ) : (
        <DataTableFrame className="max-h-96">
          <DataTable className="min-w-[44rem]">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Type</th>
                <th scope="col">Technician</th>
                <th scope="col">Activity</th>
                <th scope="col" className="text-right">
                  Captures
                </th>
                <th scope="col">Summary</th>
                {canOpen && <th scope="col">Report</th>}
              </tr>
            </thead>
            <tbody>
              {visits.map((v) => (
                <tr key={v.day} className="align-top">
                  <td className="whitespace-nowrap">{fullDay(v.day)}</td>
                  <td>{visitType(v.visit_type)}</td>
                  <td>{v.technicians.join(", ") || "—"}</td>
                  <td className="whitespace-nowrap">
                    <span className="inline-flex items-center gap-1.5">
                      <ActivityDot value={v.activity} /> {level(v.activity)}
                    </span>
                  </td>
                  <td className="text-right">{v.captures || "—"}</td>
                  <td>{v.summaries.join(" ") || "—"}</td>
                  {canOpen && (
                    <td>
                      {v.report_id ? (
                        <Link
                          href={`/service-reports/${v.report_id}`}
                          className="text-primary hover:underline"
                        >
                          Open
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </DataTable>
        </DataTableFrame>
      )}
    </Section>
  );
}

function Reports({ p }: { p: StoreProfile }) {
  return (
    <Section title="Reports and Documents">
      {p.reports.length === 0 ? (
        <Empty>No generated reports at this store yet.</Empty>
      ) : (
        <ul className="flex flex-col gap-1 text-[13px]">
          {p.reports.map((r) => (
            <li key={r.id}>
              <Link href={`/service-reports/${r.id}`} className="text-primary hover:underline">
                {r.title}
              </Link>{" "}
              <span className="text-xs text-muted-foreground">
                r{r.revision} · worked {fullDay(r.work_date)} · finalized {fullDay(r.finalized_on)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link
        href={`/locations/${p.location_id}?tab=documents`}
        className="text-[13px] text-primary hover:underline"
      >
        PestPac documents for this store
      </Link>
    </Section>
  );
}

function Body({ p, operatorId }: { p: StoreProfile; operatorId: string | undefined }) {
  const { can } = usePermissions();
  const canOpenReports = operatorId !== undefined && can("reports:read", operatorId);
  const n = p.numbers;
  return (
    <div className="flex flex-col gap-4 px-4 pt-5 pb-10 sm:px-7">
      <Why p={p} />
      <dl className="grid grid-cols-2 gap-2.5 lg:grid-cols-6">
        <StatTile label="Services performed" value={num(n.services)} />
        <StatTile label="Documented captures" value={num(n.captures)} />
        <StatTile label="Visits with activity" value={pct(n.activity_rate)} />
        <StatTile
          label="Activity visits, last 30 days"
          value={n.rated_30d ? `${n.activity_30d} of ${n.rated_30d}` : "—"}
        />
        <StatTile label="Open structural items" value={num(n.structural_open)} />
        <StatTile
          label="Days since last service"
          value={n.days_since_service === null ? "—" : num(n.days_since_service)}
        />
      </dl>
      <Journey p={p} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Trend p={p} />
        <ActivityGrid p={p} />
      </div>
      <RecentServices visits={p.visits} canOpen={canOpenReports} />
      {p.assessments.length > 0 && (
        <Section
          title="Risk Assessment History"
          note="Risk assessments from GoCanvas: every zone scored 1 (low) to 5 (critical) for sanitation and structural integrity, with rodent and pest evidence."
        >
          {p.assessments.map((a, i) => (
            <Assessment key={a.inspection_id} a={a} open={i === 0} />
          ))}
        </Section>
      )}
      <Eyebrow className="mt-2 text-muted-foreground">Full store history</Eyebrow>
      <ProgramRecord p={p} />
      <Timeline visits={p.visits} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Section
          title="Open Structural Vulnerabilities"
          note="The latest report of each distinct vulnerability still open."
        >
          <FindingTable status findings={p.open_structural} empty="None open." />
        </Section>
        <Section title="Recent Sanitation and Pest Findings" note="The most recent 12.">
          <FindingTable status={false} findings={p.recent_concerns} empty="None logged." />
        </Section>
      </div>
      <ServiceLog visits={p.visits} canOpen={canOpenReports} />
      {canOpenReports && <Reports p={p} />}
    </div>
  );
}

function CopyLink() {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("copied");
    } catch (error) {
      console.error("Could not copy the store link", error);
      setState("failed");
    }
  };
  return (
    <Button variant="ghost" size="sm" className={HEAD_BUTTON} onClick={copy}>
      {state === "copied" ? "Link copied" : state === "failed" ? "Couldn't copy" : "Copy link"}
    </Button>
  );
}

const HEAD_BUTTON = "border border-white/25 text-white hover:bg-white/15 hover:text-white";

/** A store's flyover: opens over the dashboard from `?store=`, so a link to it can be shared. */
export function StoreProfileDrawer({
  companyId,
  operatorId,
}: {
  companyId: string;
  operatorId: string | undefined;
}) {
  const [locationId, setLocationId] = useStoreParam();
  const { can } = usePermissions();
  const profile = useDashboardGetStoreProfile(companyId, locationId ?? "", {
    query: { enabled: Boolean(locationId) },
  });
  const p = profile.data?.data;
  const attention = p && ATTENTION[p.attention as keyof typeof ATTENTION];
  const staff = operatorId !== undefined && can("bill_tos:read", operatorId);
  return (
    <Dialog open={Boolean(locationId)} onOpenChange={(open) => !open && setLocationId(null)}>
      <DialogPortal>
        <DialogOverlay className="bg-black/55" />
        <DialogPrimitive.Popup className="fixed top-0 right-0 z-50 h-full w-full overflow-y-auto overscroll-contain bg-muted text-sm text-popover-foreground shadow-2xl duration-200 outline-none sm:max-w-[1180px] data-open:animate-in data-open:fade-in-0 data-open:slide-in-from-right-10 data-closed:animate-out data-closed:fade-out-0 data-closed:slide-out-to-right-10">
          <header className="sticky top-0 z-10 flex flex-wrap items-start justify-between gap-4 border-b-4 border-chart-1 bg-ink px-4 pt-5 pb-4 text-white sm:px-7">
            <div className="flex min-w-0 flex-[1_1_26rem] flex-col gap-1">
              <Eyebrow className="text-highlight">
                Store profile
                {p?.store_number ? ` · #${p.store_number}` : ""}
                {p?.state ? ` · ${p.state}` : ""}
              </Eyebrow>
              <DialogTitle className="text-2xl leading-tight font-bold sm:text-3xl">
                {p?.name ?? "Store"}
              </DialogTitle>
              {p && (
                <p className="text-[13px] text-ink-muted">
                  {[p.address, p.city, p.state].filter(Boolean).join(", ")}
                </p>
              )}
              {p && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {attention && (
                    <Badge variant={attention.variant}>
                      <span aria-hidden className="size-1.5 rounded-full bg-current" />
                      {attention.label}
                    </Badge>
                  )}
                  {[p.stage, p.tier].filter(Boolean).map((tag) => (
                    <span
                      key={tag}
                      className="rounded-4xl border border-white/15 bg-white/10 px-2.5 py-0.5 text-[11px] font-bold"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {staff && p && (
                <Link
                  href={`/locations/${p.location_id}`}
                  className={buttonVariants({
                    variant: "ghost",
                    size: "sm",
                    className: HEAD_BUTTON,
                  })}
                >
                  Open store page
                </Link>
              )}
              <CopyLink />
              <DialogClose
                render={<Button size="sm" className="bg-white text-foreground hover:bg-white/85" />}
              >
                Close
              </DialogClose>
            </div>
          </header>
          {profile.isPending && locationId && (
            <p className="p-7 text-muted-foreground">Loading store…</p>
          )}
          {profile.isError && (
            <div className="p-7">
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(profile.error, "Could not load this store.")}
                </AlertDescription>
              </Alert>
            </div>
          )}
          {p && <Body p={p} operatorId={operatorId} />}
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
