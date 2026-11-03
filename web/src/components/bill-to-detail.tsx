"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useCallback } from "react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { LocationsTable } from "@/components/locations-table";
import { BillToRiskInspections } from "@/components/risk-inspections-list";
import { BillToDetailLines } from "@/components/bill-to-onboarding";
import { LocationSyncResult } from "@/components/location-sync-result";
import { InvoicedOrders } from "@/components/invoiced-orders";
import { PostedServiceOrders } from "@/components/posted-service-orders";
import { PestPacSync } from "@/components/sync-job-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/page-tabs";
import { useDocumentTitle } from "@/lib/use-document-title";
import { errorMessage } from "@/lib/api/errors";
import {
  getBillTosGetBillToQueryKey,
  getBillTosListLocationsQueryKey,
  useBillTosGetBillTo,
  useBillTosListLocations,
  useBillTosRefreshBillTo,
  useBillTosUpdateBillTo,
} from "@/lib/api/generated/bill-tos/bill-tos";
import { usePermissions } from "@/lib/permissions";
import { useUrlTab } from "@/lib/use-url-tab";

/** Whether this bill-to's orders have findings extracted when they post. Future orders only: the
 * backlog is queued by `python -m app.extract_findings`. */
function ExtractFindings({
  billToId,
  on,
  active,
}: {
  billToId: string;
  on: boolean;
  active: boolean;
}) {
  const queryClient = useQueryClient();
  const update = useBillTosUpdateBillTo({
    mutation: {
      onSuccess: () =>
        queryClient.invalidateQueries({ queryKey: getBillTosGetBillToQueryKey(billToId) }),
    },
  });
  return (
    <section
      aria-labelledby="extract-findings"
      className="rounded-lg border border-border bg-card px-4 py-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="extract-findings" className="sr-only">
            Extract findings
          </h2>
          <span className="flex items-center gap-2 font-medium">
            Extract findings
            {on && <Badge variant="success">Active</Badge>}
          </span>
          <p className="text-sm text-muted-foreground">
            Reads the notes of orders as they post. Sends them to OpenRouter.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={!active || update.isPending}
          onClick={() => update.mutate({ billToId, data: { extract_findings: !on } })}
        >
          {on ? "Deactivate" : "Activate"}
        </Button>
      </div>
      {update.isError && (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{errorMessage(update.error)}</AlertDescription>
        </Alert>
      )}
    </section>
  );
}

export function BillToDetail() {
  const { billToId } = useParams<{ billToId: string }>();
  const [tab, setTab] = useUrlTab(["locations", "posted", "invoiced", "open", "risk"], "locations");
  const queryClient = useQueryClient();
  const { can } = usePermissions();
  const billTo = useBillTosGetBillTo(billToId);
  const locations = useBillTosListLocations(billToId);
  useDocumentTitle(billTo.data?.data.name, billTo.data?.data.trail.at(-1)?.name);
  const onSynced = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: getBillTosListLocationsQueryKey(billToId) });
    // Expanded locations' orders (keys are `/v1/locations/{id}/service-orders`).
    queryClient.invalidateQueries({
      predicate: (q) => String(q.queryKey[0]).endsWith("/service-orders"),
    });
  }, [queryClient, billToId]);
  // Documents and conditions are listed per location; refetch any that are open.
  const onSyncedLocations = useCallback(() => {
    queryClient.invalidateQueries({
      predicate: (q) => /\/(documents|conditions)$/.test(String(q.queryKey[0])),
    });
  }, [queryClient]);
  const refresh = useBillTosRefreshBillTo({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getBillTosGetBillToQueryKey(billToId) });
        queryClient.invalidateQueries({ queryKey: getBillTosListLocationsQueryKey(billToId) });
      },
    },
  });

  if (billTo.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (billTo.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(billTo.error, "Bill-to not found.")}</AlertDescription>
      </Alert>
    );
  }
  const b = billTo.data.data;
  const canWrite = can("bill_tos:write", b.operator_id);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs trail={b.trail} />
        <h1 className="mt-2 flex flex-wrap items-center gap-3 text-3xl">
          {b.name}
          {!b.is_active && <Badge variant="outline">Inactive</Badge>}
        </h1>
        <p className="text-muted-foreground">
          {[
            `BillToID ${b.pestpac_bill_to_id}`,
            b.pestpac_bill_to_code && `code ${b.pestpac_bill_to_code}`,
            b.pestpac_type,
            b.phone,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {b.description && <p className="text-muted-foreground">{b.description}</p>}
        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-primary hover:underline">
            PestPac details
          </summary>
          <div className="mt-3 flex flex-col gap-4 border-l-2 border-border pl-4">
            <BillToDetailLines details={b} />
            <p className="text-xs text-muted-foreground">
              {b.pestpac_fetched_at
                ? `From PestPac ${new Date(b.pestpac_fetched_at).toLocaleString()}`
                : "Not fetched from PestPac yet."}
            </p>
            {canWrite && (
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={refresh.isPending}
                  onClick={() => refresh.mutate({ billToId })}
                >
                  {refresh.isPending ? "Refreshing…" : "Refresh from PestPac"}
                </Button>
              </div>
            )}
          </div>
        </details>
        {refresh.isSuccess && (
          <LocationSyncResult summary={refresh.data.data.locations_sync} label="Refreshed" />
        )}
        {refresh.isError && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(refresh.error)}</AlertDescription>
          </Alert>
        )}
      </div>

      <PestPacSync
        billToId={billToId}
        canSync={canWrite && b.is_active}
        onOrdersSynced={onSynced}
        onLocationSynced={onSyncedLocations}
      />

      {canWrite && (
        <ExtractFindings billToId={billToId} on={b.extract_findings} active={b.is_active} />
      )}

      {/* Invoiced orders need billing:read; a URL naming it falls back for others. */}
      <Tabs
        value={tab === "invoiced" && !can("billing:read", b.operator_id) ? "locations" : tab}
        onValueChange={setTab}
      >
        <TabsList>
          <TabsTrigger value="locations">Locations</TabsTrigger>
          <TabsTrigger value="posted">Posted Service Orders</TabsTrigger>
          {can("billing:read", b.operator_id) && (
            <TabsTrigger value="invoiced">Invoiced Orders</TabsTrigger>
          )}
          <TabsTrigger value="open">Open Orders</TabsTrigger>
          <TabsTrigger value="risk">Risk Inspections</TabsTrigger>
        </TabsList>
        <TabsContent value="locations" className="pt-4">
          <LocationsTable locations={locations} exportName={`${b.name} locations`} />
        </TabsContent>
        <TabsContent value="posted" className="pt-4">
          <PostedServiceOrders
            billToId={billToId}
            companyId={b.company_id}
            operatorId={b.operator_id}
          />
        </TabsContent>
        {can("billing:read", b.operator_id) && (
          <TabsContent value="invoiced" className="pt-4">
            <InvoicedOrders billToId={billToId} />
          </TabsContent>
        )}
        <TabsContent value="open" className="pt-4">
          <PostedServiceOrders
            kind="open"
            billToId={billToId}
            companyId={b.company_id}
            operatorId={b.operator_id}
          />
        </TabsContent>
        <TabsContent value="risk" className="pt-4">
          <BillToRiskInspections billToId={billToId} billToName={b.name} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
