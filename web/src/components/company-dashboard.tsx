"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { ProgramOverview } from "@/components/program-overview";
import {
  ExecutiveTabView,
  RiskModelTabView,
  RodentActivityTabView,
  SanitationTabView,
  StoreScorecardTabView,
  StructuralTabView,
  TrackerTabView,
} from "@/components/program-tabs";
import { ReportLibrary } from "@/components/report-library";
import { RiskAssessmentsTabView } from "@/components/risk-assessment-dashboard";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/page-tabs";
import { useDocumentTitle } from "@/lib/use-document-title";
import { errorMessage } from "@/lib/api/errors";
import {
  useCompaniesGetCompany,
  useCompaniesListBillTos,
} from "@/lib/api/generated/companies/companies";
import { useDashboardGetCompanyDashboard } from "@/lib/api/generated/dashboard/dashboard";
import type {
  CompanyDashboard,
  MonthCount,
  ServiceCodeCount,
  StoreRow,
} from "@/lib/api/generated/model";
import { usePermissions } from "@/lib/permissions";
import { useUrlTab } from "@/lib/use-url-tab";

const DAY_MS = 864e5;
const integer = new Intl.NumberFormat();
const compact = new Intl.NumberFormat(undefined, { notation: "compact" });

/** PestPac dates are local wall-clock times without an offset; show them as-is. */
function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—";
}

function formatMonth(month: string, style: "short" | "long" = "short") {
  const [year, m] = month.split("-").map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString(undefined, {
    month: style,
    year: style === "short" ? "2-digit" : "numeric",
  });
}

function daysSince(asOf: string, value: string | null) {
  if (!value) return null;
  return Math.max(0, Math.floor((Date.parse(asOf) - new Date(value).getTime()) / DAY_MS));
}

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card p-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold">{value}</span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  );
}

const servicesConfig = {
  services: { label: "Services", color: "var(--chart-1)" },
} satisfies ChartConfig;

/** A chart's data as a table, for screen readers and exact values. */
function DataTable({ caption, rows }: { caption: string; rows: [string, number][] }) {
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-primary hover:underline">Show table</summary>
      <table className="mt-2 w-full max-w-sm">
        <caption className="sr-only">{caption}</caption>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-border last:border-0">
              <th scope="row" className="py-1 text-left font-normal">
                {label}
              </th>
              <td className="py-1 text-right tabular-nums">{integer.format(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function ServicesByMonth({ data }: { data: MonthCount[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Services by month</CardTitle>
        <CardDescription>Worked orders, by work date</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ChartContainer config={servicesConfig} className="aspect-auto h-64 w-full">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(m: string) => formatMonth(m)}
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              width={36}
              tickFormatter={(v: number) => compact.format(v)}
            />
            <ChartTooltip
              cursor={{ fill: "var(--muted)" }}
              content={
                <ChartTooltipContent labelFormatter={(m) => formatMonth(String(m), "long")} />
              }
            />
            <Bar
              dataKey="services"
              fill="var(--color-services)"
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
            />
          </BarChart>
        </ChartContainer>
        <DataTable
          caption="Services by month"
          rows={data.map((d) => [formatMonth(d.month, "long"), d.services])}
        />
      </CardContent>
    </Card>
  );
}

const MAX_CODES = 10;

function ServicesByCode({ data }: { data: ServiceCodeCount[] }) {
  const rows = useMemo(() => {
    const named = data.map((d) => ({ code: d.service_code ?? "No code", services: d.services }));
    if (named.length <= MAX_CODES) return named;
    const other = named.slice(MAX_CODES - 1).reduce((t, d) => t + d.services, 0);
    return [...named.slice(0, MAX_CODES - 1), { code: "Other codes", services: other }];
  }, [data]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Services by service code</CardTitle>
        <CardDescription>Worked orders, by PestPac service code</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ChartContainer
          config={servicesConfig}
          className="aspect-auto w-full"
          style={{ height: Math.max(rows.length * 36, 72) }}
        >
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid horizontal={false} stroke="var(--border)" />
            <XAxis
              type="number"
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => compact.format(v)}
            />
            <YAxis type="category" dataKey="code" tickLine={false} axisLine={false} width={130} />
            <ChartTooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltipContent />} />
            <Bar
              dataKey="services"
              fill="var(--color-services)"
              radius={[0, 4, 4, 0]}
              maxBarSize={24}
            />
          </BarChart>
        </ChartContainer>
        <DataTable
          caption="Services by service code"
          rows={rows.map((r) => [r.code, r.services])}
        />
      </CardContent>
    </Card>
  );
}

function Overview({ d }: { d: CompanyDashboard }) {
  const h = d.headline;
  return (
    <div className="flex flex-col gap-6">
      {h.services === 0 && (
        <Alert>
          <AlertDescription>
            No worked service orders yet. Use “Sync service orders” on a bill-to or location page
            (with the background worker running) to pull them from PestPac.
          </AlertDescription>
        </Alert>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile
          label="Locations"
          value={integer.format(h.locations)}
          note={`${integer.format(h.locations_serviced)} serviced`}
        />
        <StatTile
          label="Services"
          value={integer.format(h.services)}
          note={
            h.first_service
              ? `${formatDate(h.first_service)} to ${formatDate(h.last_service)}`
              : undefined
          }
        />
        <StatTile label="Open orders" value={integer.format(h.open_orders)} />
        <StatTile label="Technicians" value={integer.format(h.technicians)} />
        <StatTile label="Awaiting billing" value={integer.format(h.awaiting_billing)} />
        <StatTile label="Billed" value={integer.format(h.billed)} />
        <StatTile label="Last service" value={formatDate(h.last_service)} />
      </div>
      {d.services_by_month.length > 0 && <ServicesByMonth data={d.services_by_month} />}
      <div className="grid gap-6 lg:grid-cols-2">
        {d.services_by_code.length > 0 && <ServicesByCode data={d.services_by_code} />}
        {d.top_technicians.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Top technicians</CardTitle>
              <CardDescription>By worked orders</CardDescription>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-2 font-medium">Technician</th>
                    <th className="py-2 text-right font-medium">Services</th>
                  </tr>
                </thead>
                <tbody>
                  {d.top_technicians.map((t) => (
                    <tr
                      key={`${t.technician_id}-${t.name}`}
                      className="border-b border-border last:border-0"
                    >
                      <td className="py-2">{t.name ?? "Unknown"}</td>
                      <td className="py-2 text-right tabular-nums">{integer.format(t.services)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

type SortKey = "store" | "name" | "services" | "open_orders" | "last_service";

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "store", label: "Store #" },
  { key: "name", label: "Location" },
  { key: "services", label: "Services", numeric: true },
  { key: "open_orders", label: "Open orders", numeric: true },
  { key: "last_service", label: "Last service" },
];

function sortValue(row: StoreRow, key: SortKey): string | number {
  switch (key) {
    case "store":
      return row.store_number ? Number(row.store_number) : Number.MAX_SAFE_INTEGER;
    case "name":
      return row.name ?? "";
    case "last_service":
      return row.last_service ?? "";
    default:
      return row[key];
  }
}

/** `linked`: store names open their location pages (not for a customer's users, who can't). */
function Stores({ d, linked }: { d: CompanyDashboard; linked: boolean }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({
    key: "services",
    desc: true,
  });
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? d.stores.filter((s) =>
          [s.name, s.store_number, s.city, s.state].some((v) => v?.toLowerCase().includes(q)),
        )
      : d.stores;
    return [...filtered].sort((a, b) => {
      const x = sortValue(a, sort.key);
      const y = sortValue(b, sort.key);
      const order = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -order : order;
    });
  }, [d.stores, query, sort]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:max-w-xs">
        <Label htmlFor="store-search">Find a location</Label>
        <Input
          id="store-search"
          type="search"
          placeholder="Store number, name, or city"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <p className="text-sm text-muted-foreground">
        {integer.format(rows.length)} of {integer.format(d.stores.length)} locations
      </p>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              {COLUMNS.map((c) => {
                const active = sort.key === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"}
                    className={c.numeric ? "p-3 text-right" : "p-3"}
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-medium text-muted-foreground hover:text-foreground"
                      onClick={() =>
                        setSort({ key: c.key, desc: active ? !sort.desc : Boolean(c.numeric) })
                      }
                    >
                      {c.label}
                      {active &&
                        (sort.desc ? (
                          <ArrowDown className="size-3" aria-hidden />
                        ) : (
                          <ArrowUp className="size-3" aria-hidden />
                        ))}
                    </button>
                  </th>
                );
              })}
              <th scope="col" className="p-3 text-right font-medium text-muted-foreground">
                Days since
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const days = daysSince(d.as_of, s.last_service);
              return (
                <tr key={s.location_id} className="border-b border-border last:border-0">
                  <td className="p-3 tabular-nums">{s.store_number ?? "—"}</td>
                  <td className="p-3">
                    {linked ? (
                      <Link
                        href={`/locations/${s.location_id}`}
                        className="text-primary hover:underline"
                      >
                        {s.name ?? `LocationID ${s.pestpac_location_id}`}
                      </Link>
                    ) : (
                      (s.name ?? `LocationID ${s.pestpac_location_id}`)
                    )}
                    <span className="block text-xs text-muted-foreground">
                      {[s.city, s.state].filter(Boolean).join(", ")}
                    </span>
                  </td>
                  <td className="p-3 text-right tabular-nums">{integer.format(s.services)}</td>
                  <td className="p-3 text-right tabular-nums">{integer.format(s.open_orders)}</td>
                  <td className="p-3">{formatDate(s.last_service)}</td>
                  <td className="p-3 text-right tabular-nums">
                    {days === null ? "—" : integer.format(days)}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-muted-foreground">
                  No locations match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const PROGRAM_TABS = [
  ["overview", "Overview"],
  ["executive", "Executive review"],
  ["assessments", "Risk assessments"],
  ["tracker", "Store tracker"],
  ["activity", "Rodent activity"],
  ["structural", "Structural"],
  ["sanitation", "Sanitation & pests"],
  ["stores", "Stores"],
  ["risk", "Risk model"],
] as const;

export function CompanyDashboardView() {
  const { companyId } = useParams<{ companyId: string }>();
  const [tab, setTab] = useUrlTab([...PROGRAM_TABS.map(([value]) => value), "reports"], "overview");
  const { can, me } = usePermissions();
  const [billToId, setBillToId] = useState("");
  const [market, setMarket] = useState("");
  const company = useCompaniesGetCompany(companyId);
  // A customer's user (company grant only) sees the dashboard alone: no bill-tos, store pages,
  // or the pages above the company. Staff see the company through their operator.
  const operatorId =
    company.data?.data.operator_id ??
    me?.company_memberships.find((g) => g.company_id === companyId)?.operator_id;
  const staff = operatorId !== undefined && can("bill_tos:read", operatorId);
  const billTos = useCompaniesListBillTos(companyId, { query: { enabled: staff } });
  useDocumentTitle("Dashboard", company.data?.data.name);
  const dashboard = useDashboardGetCompanyDashboard(
    companyId,
    billToId ? { bill_to_id: billToId } : undefined,
  );

  if (company.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(company.error, "Company not found.")}</AlertDescription>
      </Alert>
    );
  }
  const c = company.data?.data;
  const program = staff && operatorId !== undefined && can("dashboards:read", operatorId);
  const scope = { companyId, billToId, state: market };
  const markets = [
    ...new Set(dashboard.data?.data.stores.flatMap((s) => (s.state ? [s.state] : [])) ?? []),
  ].sort();

  return (
    <div className="flex flex-col gap-6">
      <div>
        {c && staff && (
          <Breadcrumbs trail={[...c.trail, { kind: "company", id: c.id, name: c.name }]} />
        )}
        <h1 className="mt-2 text-3xl">{c ? `${c.name} dashboard` : "Dashboard"}</h1>
        <p className="text-muted-foreground">
          Service activity from PestPac
          {dashboard.data && ` · as of ${new Date(dashboard.data.data.as_of).toLocaleString()}`}
        </p>
      </div>

      {staff && (
        <div className="flex flex-wrap gap-4">
          <div className="flex w-full flex-col gap-2 sm:max-w-sm">
            <Label htmlFor="dashboard-bill-to">Bill-to</Label>
            <NativeSelect
              id="dashboard-bill-to"
              className="w-full"
              value={billToId}
              onChange={(e) => setBillToId(e.target.value)}
            >
              <NativeSelectOption value="">All bill-tos</NativeSelectOption>
              {billTos.data?.data.map((b) => (
                <NativeSelectOption key={b.id} value={b.id}>
                  {b.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="dashboard-market">Market</Label>
            <NativeSelect
              id="dashboard-market"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
            >
              <NativeSelectOption value="">All markets</NativeSelectOption>
              {markets.map((m) => (
                <NativeSelectOption key={m} value={m}>
                  {m}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        </div>
      )}

      {dashboard.isPending && <p className="text-muted-foreground">Loading…</p>}
      {dashboard.isError && (
        <Alert variant="destructive">
          <AlertDescription>
            {errorMessage(dashboard.error, "Could not load the dashboard.")}
          </AlertDescription>
        </Alert>
      )}
      {dashboard.data && (
        <Tabs value={tab} onValueChange={setTab}>
          <div className="overflow-x-auto">
            <TabsList>
              {program ? (
                PROGRAM_TABS.map(([value, label]) => (
                  <TabsTrigger key={value} value={value}>
                    {label}
                  </TabsTrigger>
                ))
              ) : (
                <>
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="stores">Stores</TabsTrigger>
                </>
              )}
              {c && can("reports:read", c.operator_id) && (
                <TabsTrigger value="reports">Reports</TabsTrigger>
              )}
            </TabsList>
          </div>
          <TabsContent value="overview" className="flex flex-col gap-8 pt-4">
            {/* Program results come from findings, which are internal: staff only. */}
            {program ? (
              <ProgramOverview companyId={companyId} billToId={billToId} state={market} />
            ) : (
              <Overview d={dashboard.data.data} />
            )}
          </TabsContent>
          <TabsContent value="stores" className="pt-4">
            {program ? (
              <StoreScorecardTabView scope={scope} />
            ) : (
              <Stores d={dashboard.data.data} linked={staff} />
            )}
          </TabsContent>
          {program && (
            <>
              <TabsContent value="executive" className="pt-4">
                <ExecutiveTabView scope={scope} />
              </TabsContent>
              <TabsContent value="assessments" className="pt-4">
                <RiskAssessmentsTabView scope={scope} />
              </TabsContent>
              <TabsContent value="tracker" className="pt-4">
                <TrackerTabView scope={scope} />
              </TabsContent>
              <TabsContent value="activity" className="pt-4">
                <RodentActivityTabView scope={scope} />
              </TabsContent>
              <TabsContent value="structural" className="pt-4">
                <StructuralTabView scope={scope} />
              </TabsContent>
              <TabsContent value="sanitation" className="pt-4">
                <SanitationTabView scope={scope} />
              </TabsContent>
              <TabsContent value="risk" className="pt-4">
                <RiskModelTabView scope={scope} />
              </TabsContent>
            </>
          )}
          {c && can("reports:read", c.operator_id) && (
            <TabsContent value="reports" className="flex flex-col gap-6 pt-4">
              {program && <ReportLibrary scope={scope} />}
              <p className="text-sm text-muted-foreground">
                Download a report from a location&apos;s page (Stores tab → location).
              </p>
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  );
}
