"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { BAND_COLOR, day, Eyebrow, pct } from "@/components/program-overview";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { errorMessage } from "@/lib/api/errors";
import {
  useDashboardGetRiskAssessmentDashboard,
  useDashboardGetRiskAssessmentFindings,
} from "@/lib/api/generated/dashboard/dashboard";
import type { AssessedStore, RiskAssessmentDashboard } from "@/lib/api/generated/model";

const integer = new Intl.NumberFormat();
const CLASSES = ["Critical", "High", "Moderate", "Low"] as const;
const CLASS_COLOR: Record<string, string> = {
  Critical: BAND_COLOR.Critical,
  High: BAND_COLOR.High,
  Moderate: BAND_COLOR.Elevated,
  Low: BAND_COLOR.Controlled,
};
const TABLE_HEAD = "bg-muted text-left text-muted-foreground";
const FINDINGS_PAGE = 50;

type Scope = { companyId: string; billToId: string; state: string };

function params({ billToId, state }: Scope) {
  return { ...(billToId ? { bill_to_id: billToId } : {}), ...(state ? { state } : {}) };
}

function one(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}

function Bars({
  rows,
}: {
  rows: { label: string; value: number; color: string; note?: string }[];
}) {
  const most = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => (
        <li key={r.label} className="grid grid-cols-[8rem_1fr_3.5rem] items-center gap-2 text-sm">
          <span>
            {r.label}
            {r.note && <span className="block text-xs text-muted-foreground">{r.note}</span>}
          </span>
          <span
            aria-hidden
            className="h-3"
            style={{ background: r.color, width: `${(r.value / most) * 100}%` }}
          />
          <span className="text-right tabular-nums">{integer.format(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

function SimpleCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function StoreCell({ s }: { s: AssessedStore }) {
  return (
    <>
      <Link
        href={`/risk-inspections/${s.inspection_id}`}
        className="font-medium text-primary hover:underline"
      >
        {s.store_number ? `#${s.store_number}` : s.name}
      </Link>
      <span className="block text-xs text-muted-foreground">
        {[s.store_number ? s.name : null, s.city, s.state].filter(Boolean).join(" · ")}
      </span>
    </>
  );
}

function ZoneDrivers({ d }: { d: RiskAssessmentDashboard }) {
  return (
    <SimpleCard
      title="Key risk drivers by zone"
      description="Latest assessment per restaurant. Zones are scored 1 (low) to 5 (critical), ranked by rodent activity."
    >
      <div className="overflow-x-auto border border-border">
        <table className="w-full min-w-[760px] text-sm">
          <thead className={TABLE_HEAD}>
            <tr>
              <th className="p-3 font-medium">Zone</th>
              <th className="p-3 text-right font-medium">Inspected</th>
              <th className="p-3 text-right font-medium">Rodent activity</th>
              <th className="p-3 text-right font-medium">Pest activity</th>
              <th className="p-3 text-right font-medium">Avg sanitation</th>
              <th className="p-3 text-right font-medium">Avg structural</th>
              <th className="p-3 text-right font-medium">Tier 3 · 4 · 5</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {d.zones.map((z) => (
              <tr key={z.zone} className="align-top">
                <td className="p-3 font-medium">{z.zone}</td>
                <td className="p-3 text-right tabular-nums">{integer.format(z.inspected)}</td>
                <td className="p-3 text-right tabular-nums">{pct(z.rodent_rate)}</td>
                <td className="p-3 text-right tabular-nums">{pct(z.pest_rate)}</td>
                <td className="p-3 text-right tabular-nums">{one(z.avg_sanitation)}</td>
                <td className="p-3 text-right tabular-nums">{one(z.avg_structural)}</td>
                <td className="p-3 text-right tabular-nums">
                  {z.tier3} · {z.tier4} · {z.tier5}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimpleCard>
  );
}

function StoreTable({ d }: { d: RiskAssessmentDashboard }) {
  const [query, setQuery] = useState("");
  const [classification, setClassification] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [rodents, setRodents] = useState(false);
  const [all, setAll] = useState(false);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return d.stores.filter(
      (s) =>
        (!classification || s.classification === classification) &&
        (!recommendation || s.recommendation === recommendation) &&
        (!rodents || s.rodent_zones > 0) &&
        (!q || [s.store_number, s.name, s.city].some((v) => (v ?? "").toLowerCase().includes(q))),
    );
  }, [d.stores, query, classification, recommendation, rodents]);
  const shown = all ? rows : rows.slice(0, 25);
  return (
    <SimpleCard
      title="Store inspection summary"
      description="Every assessed restaurant with its latest result. Open a store for the full zone-by-zone assessment."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-56 flex-col gap-1">
            <Label htmlFor="ra-find">Find a store</Label>
            <Input
              id="ra-find"
              type="search"
              placeholder="Store number, name, or city"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ra-class">Classification</Label>
            <NativeSelect
              id="ra-class"
              value={classification}
              onChange={(e) => setClassification(e.target.value)}
            >
              <NativeSelectOption value="">All classifications</NativeSelectOption>
              {CLASSES.map((c) => (
                <NativeSelectOption key={c} value={c}>
                  {c}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ra-rec">Recommendation</Label>
            <NativeSelect
              id="ra-rec"
              value={recommendation}
              onChange={(e) => setRecommendation(e.target.value)}
            >
              <NativeSelectOption value="">All recommendations</NativeSelectOption>
              {["RAMP 1", "RAMP 2", "RAMP 3"].map((r) => (
                <NativeSelectOption key={r} value={r}>
                  {r}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={rodents}
              onChange={(e) => setRodents(e.target.checked)}
            />
            Rodent activity only
          </label>
          <p className="ml-auto text-sm text-muted-foreground">
            {integer.format(rows.length)} of {integer.format(d.stores.length)} stores
          </p>
        </div>
        <div className="overflow-x-auto border border-border">
          <table className="w-full min-w-[820px] text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Assessed</th>
                <th className="p-3 font-medium">Classification</th>
                <th className="p-3 font-medium">Recommendation</th>
                <th className="p-3 text-right font-medium">Risk index</th>
                <th className="p-3 text-right font-medium">Sanitation</th>
                <th className="p-3 text-right font-medium">Structural</th>
                <th className="p-3 text-right font-medium">Rodent zones</th>
                <th className="p-3 text-right font-medium">Assessments</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((s) => (
                <tr key={s.location_id} className="align-top">
                  <td className="p-3">
                    <StoreCell s={s} />
                  </td>
                  <td className="p-3 whitespace-nowrap">{day(s.assessed_on)}</td>
                  <td className="p-3 whitespace-nowrap">
                    <span
                      aria-hidden
                      className="mr-2 inline-block size-2.5"
                      style={{ background: CLASS_COLOR[s.classification ?? ""] ?? "var(--border)" }}
                    />
                    {s.classification ?? "—"}
                  </td>
                  <td className="p-3 whitespace-nowrap">{s.recommendation ?? "—"}</td>
                  <td className="p-3 text-right tabular-nums">{one(s.risk_index)}</td>
                  <td className="p-3 text-right tabular-nums">{one(s.sanitation_index)}</td>
                  <td className="p-3 text-right tabular-nums">{one(s.structural_index)}</td>
                  <td className="p-3 text-right tabular-nums">{s.rodent_zones}</td>
                  <td className="p-3 text-right tabular-nums">{s.assessments}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 25 && (
          <Button variant="outline" className="self-center" onClick={() => setAll(!all)}>
            {all ? "Show fewer" : `Show all ${integer.format(rows.length)} stores`}
          </Button>
        )}
      </div>
    </SimpleCard>
  );
}

function Findings({ scope }: { scope: Scope }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [zone, setZone] = useState("");
  const [page, setPage] = useState(0);
  const findings = useDashboardGetRiskAssessmentFindings(scope.companyId, {
    ...params(scope),
    ...(query.trim() ? { q: query.trim() } : {}),
    ...(kind ? { kind } : {}),
    ...(zone ? { zone } : {}),
    limit: FINDINGS_PAGE,
    offset: page * FINDINGS_PAGE,
  });
  const data = findings.data?.data;
  const pages = data ? Math.ceil(data.total / FINDINGS_PAGE) : 0;
  return (
    <SimpleCard
      title="Detailed inspection findings"
      description="Every written finding from the assessments, zone by zone, newest first."
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-72 flex-col gap-1">
            <Label htmlFor="ra-findings-find">Search findings</Label>
            <Input
              id="ra-findings-find"
              type="search"
              placeholder="e.g. door sweep, standing water, droppings"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ra-findings-kind">Finding type</Label>
            <NativeSelect
              id="ra-findings-kind"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setPage(0);
              }}
            >
              <NativeSelectOption value="">All types</NativeSelectOption>
              {["Pest", "Structural", "Sanitation", "Note"].map((k) => (
                <NativeSelectOption key={k} value={k}>
                  {k}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="ra-findings-zone">Zone</Label>
            <NativeSelect
              id="ra-findings-zone"
              className="max-w-64"
              value={zone}
              onChange={(e) => {
                setZone(e.target.value);
                setPage(0);
              }}
            >
              <NativeSelectOption value="">All zones</NativeSelectOption>
              {(data?.zones ?? []).map((z) => (
                <NativeSelectOption key={z} value={z}>
                  {z}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          {data && (
            <p className="ml-auto text-sm text-muted-foreground">
              {integer.format(data.total)} findings
            </p>
          )}
        </div>
        {findings.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {errorMessage(findings.error, "Could not load the findings.")}
            </AlertDescription>
          </Alert>
        )}
        <div className="overflow-x-auto border border-border">
          <table className="w-full min-w-[720px] text-sm">
            <thead className={TABLE_HEAD}>
              <tr>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Date</th>
                <th className="p-3 font-medium">Zone</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium">Finding</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {(data?.items ?? []).map((f, i) => (
                <tr key={`${f.inspection_id}-${f.zone}-${f.kind}-${i}`} className="align-top">
                  <td className="p-3 whitespace-nowrap">
                    <Link
                      href={`/risk-inspections/${f.inspection_id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {f.store_number ? `#${f.store_number}` : f.name}
                    </Link>
                  </td>
                  <td className="p-3 whitespace-nowrap">{day(f.assessed_on)}</td>
                  <td className="p-3">{f.zone}</td>
                  <td className="p-3">{f.kind}</td>
                  <td className="p-3">{f.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {pages > 1 && (
          <div className="flex items-center justify-center gap-3 text-sm">
            <Button variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <span>
              Page {integer.format(page + 1)} of {integer.format(pages)}
            </span>
            <Button
              variant="outline"
              disabled={page + 1 >= pages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </SimpleCard>
  );
}

export function RiskAssessmentsTabView({ scope }: { scope: Scope }) {
  const dashboard = useDashboardGetRiskAssessmentDashboard(scope.companyId, params(scope));
  if (dashboard.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (dashboard.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {errorMessage(dashboard.error, "Could not load the risk assessments.")}
        </AlertDescription>
      </Alert>
    );
  }
  const d = dashboard.data.data;
  const S = d.stores;
  const n = (test: (s: AssessedStore) => boolean) => S.filter(test).length;
  const scored = S.flatMap((s) => (s.risk_index === null ? [] : [s.risk_index]));
  const average = scored.length ? scored.reduce((t, v) => t + v, 0) / scored.length : null;
  const tiles: [string, string, string][] = [
    [
      integer.format(d.assessments),
      "Risk assessments completed",
      `${integer.format(d.zone_inspections)} zone inspections`,
    ],
    [
      integer.format(S.length),
      "Restaurants assessed",
      `${integer.format(n((s) => s.assessments > 1))} re-assessed`,
    ],
    [one(average), "Average risk index", "0–100 · latest assessment per store"],
    [
      pct(S.length ? n((s) => s.rodent_zones > 0) / S.length : null),
      "With rodent activity",
      `${integer.format(n((s) => s.rodent_zones > 0))} restaurants, any zone`,
    ],
    [
      pct(S.length ? n((s) => s.pest_zones > 0) / S.length : null),
      "With pest activity",
      `${integer.format(n((s) => s.pest_zones > 0))} restaurants, any zone`,
    ],
    [
      integer.format(n((s) => s.classification === "Critical" || s.classification === "High")),
      "High or critical",
      "a zone scored 4 or 5",
    ],
    [integer.format(n((s) => s.in_program)), "In the RAMP program", "of the restaurants assessed"],
  ];
  const repeats = S.filter((s) => s.first_index !== null && s.risk_index !== null)
    .map((s) => ({ s, change: (s.risk_index ?? 0) - (s.first_index ?? 0) }))
    .sort((a, b) => b.change - a.change);
  const site = Object.entries(
    d.site.reduce<Record<string, { value: string; stores: number }[]>>((all, c) => {
      (all[c.attribute] ??= []).push(c);
      return all;
    }, {}),
  );
  return (
    <div className="flex flex-col gap-6">
      <section className="bg-ink px-6 py-8 text-white sm:px-8">
        <Eyebrow className="text-highlight">Risk assessments</Eyebrow>
        <h2 className="mt-3 max-w-4xl text-2xl leading-snug sm:text-3xl">
          An x-ray of every restaurant
        </h2>
        <div aria-hidden className="mt-4 h-1 w-16 bg-highlight" />
        <p className="mt-4 max-w-3xl text-sm">
          Each assessment walks the restaurant zone by zone and scores rodent activity, pest
          activity, structural integrity, and sanitation from 1 (low) to 5 (critical).{" "}
          {integer.format(d.assessments)} assessments, {day(d.first)} to {day(d.last)}, from
          GoCanvas.
          {d.unlinked > 0 &&
            ` ${integer.format(d.unlinked)} more aren't matched to a store and aren't counted.`}
        </p>
      </section>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map(([value, label, note]) => (
          <div key={label} className="border border-border bg-card p-4">
            <dt className="sr-only">{label}</dt>
            <dd className="font-heading text-3xl font-bold">{value}</dd>
            <dd className="text-sm font-bold">{label}</dd>
            <dd className="text-xs text-muted-foreground">{note}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <SimpleCard
          title="Risk by market"
          description="Assessed against every location in the state, latest assessment per restaurant."
        >
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-sm">
              <thead className={TABLE_HEAD}>
                <tr>
                  <th className="p-3 font-medium">State</th>
                  <th className="p-3 text-right font-medium">Assessed</th>
                  <th className="p-3 text-right font-medium">Avg risk index</th>
                  <th className="p-3 text-right font-medium">High or critical</th>
                  <th className="p-3 text-right font-medium">With rodents</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {d.coverage.map((c) => (
                  <tr key={c.state}>
                    <td className="p-3">{c.state}</td>
                    <td className="p-3 text-right tabular-nums">
                      {integer.format(c.assessed)} of {integer.format(c.in_program)}
                    </td>
                    <td className="p-3 text-right tabular-nums">{one(c.avg_index)}</td>
                    <td className="p-3 text-right tabular-nums">{c.high_or_critical}</td>
                    <td className="p-3 text-right tabular-nums">{c.with_rodents}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SimpleCard>
        <SimpleCard title="Classification and recommendation" description="Latest per restaurant.">
          <div className="flex flex-col gap-4">
            <Bars
              rows={CLASSES.map((c) => ({
                label: c,
                value: n((s) => s.classification === c),
                color: CLASS_COLOR[c],
              }))}
            />
            <Bars
              rows={["RAMP 1", "RAMP 2", "RAMP 3"].map((r, i) => ({
                label: r,
                value: n((s) => s.recommendation === r),
                color: [CLASS_COLOR.Critical, CLASS_COLOR.High, CLASS_COLOR.Low][i],
                note: ["severe: full abatement", "moderate: targeted", "preventive"][i],
              }))}
            />
          </div>
        </SimpleCard>
      </div>
      <ZoneDrivers d={d} />
      <div className="grid gap-6 lg:grid-cols-2">
        <SimpleCard
          title="Site conditions"
          description="Building characteristics recorded at the latest assessment."
        >
          <dl className="flex flex-col gap-3 text-sm">
            {site.map(([attribute, values]) => (
              <div key={attribute}>
                <dt className="font-bold">{attribute}</dt>
                <dd className="text-muted-foreground">
                  {values.map((v) => `${v.value} (${integer.format(v.stores)})`).join(" · ")}
                </dd>
              </div>
            ))}
          </dl>
        </SimpleCard>
        <SimpleCard
          title="Re-assessments: is risk moving?"
          description="Restaurants assessed more than once, first vs. latest risk index, most worsening first."
        >
          {repeats.length === 0 ? (
            <p className="text-sm text-muted-foreground">No restaurant re-assessed yet.</p>
          ) : (
            <div className="max-h-96 overflow-auto border border-border">
              <table className="w-full text-sm">
                <thead className={TABLE_HEAD}>
                  <tr>
                    <th className="p-3 font-medium">Store</th>
                    <th className="p-3 text-right font-medium">First → latest</th>
                    <th className="p-3 text-right font-medium">Change</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {repeats.map(({ s, change }) => (
                    <tr key={s.location_id} className="align-top">
                      <td className="p-3">
                        <StoreCell s={s} />
                      </td>
                      <td className="p-3 text-right tabular-nums">
                        {one(s.first_index)} → {one(s.risk_index)}
                      </td>
                      <td className="p-3 text-right tabular-nums">
                        {change > 0 ? "+" : ""}
                        {change.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SimpleCard>
      </div>
      <StoreTable d={d} />
      <Findings scope={scope} />
    </div>
  );
}
