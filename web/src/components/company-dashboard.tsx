"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { DashboardLinksContext } from "@/components/dashboard-link";
import { ProgramOverview } from "@/components/program-overview";
import { StoreProfileDrawer } from "@/components/store-profile";
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
import { usePermissions } from "@/lib/permissions";
import { useUrlTab } from "@/lib/use-url-tab";

const PROGRAM_TABS = [
  ["overview", "Overview"],
  ["executive", "Executive Review"],
  ["assessments", "Risk Assessments"],
  ["tracker", "Store Tracker"],
  ["activity", "Rodent Activity"],
  ["structural", "Structural"],
  ["sanitation", "Sanitation & Pests"],
  ["stores", "Stores"],
  ["risk", "Risk Model"],
] as const;

export function CompanyDashboardView() {
  const { companyId } = useParams<{ companyId: string }>();
  const [tab, setTab] = useUrlTab([...PROGRAM_TABS.map(([value]) => value), "reports"], "overview");
  const { can, me } = usePermissions();
  const [billToId, setBillToId] = useState("");
  const [market, setMarket] = useState("");
  const company = useCompaniesGetCompany(companyId);
  // Everyone sees the same dashboard. A customer's user (company grant only) can't open what
  // surrounds it: bill-tos, store pages, or the pages above the company.
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
          Service activity
          {dashboard.data && ` · as of ${new Date(dashboard.data.data.as_of).toLocaleString()}`}
        </p>
      </div>

      <div className="flex flex-wrap gap-4">
        {staff && (
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
        )}
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

      {dashboard.isPending && <p className="text-muted-foreground">Loading…</p>}
      {dashboard.isError && (
        <Alert variant="destructive">
          <AlertDescription>
            {errorMessage(dashboard.error, "Could not load the dashboard.")}
          </AlertDescription>
        </Alert>
      )}
      {dashboard.data && (
        <DashboardLinksContext.Provider value={staff}>
          <Tabs value={tab} onValueChange={setTab}>
            <div className="overflow-x-auto">
              <TabsList>
                {PROGRAM_TABS.map(([value, label]) => (
                  <TabsTrigger key={value} value={value}>
                    {label}
                  </TabsTrigger>
                ))}
                {c && can("reports:read", c.operator_id) && (
                  <TabsTrigger value="reports">Reports</TabsTrigger>
                )}
              </TabsList>
            </div>
            <TabsContent value="overview" className="flex flex-col gap-8 pt-4">
              <ProgramOverview companyId={companyId} billToId={billToId} state={market} />
            </TabsContent>
            <TabsContent value="stores" className="pt-4">
              <StoreScorecardTabView scope={scope} />
            </TabsContent>
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
            {c && can("reports:read", c.operator_id) && (
              <TabsContent value="reports" className="flex flex-col gap-6 pt-4">
                <ReportLibrary scope={scope} />
                <p className="text-sm text-muted-foreground">
                  Download a report from a location&apos;s page (Stores tab → location).
                </p>
              </TabsContent>
            )}
          </Tabs>
          <StoreProfileDrawer companyId={companyId} operatorId={operatorId} />
        </DashboardLinksContext.Provider>
      )}
    </div>
  );
}
