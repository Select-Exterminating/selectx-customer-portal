"use client";

import Link from "next/link";
import { useState } from "react";

import { StoreLink } from "@/components/dashboard-link";
import { DataTable, DataTableFrame } from "@/components/data-table";
import { day } from "@/components/program-overview";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import { useDashboardGetReportLibrary } from "@/lib/api/generated/dashboard/dashboard";

const integer = new Intl.NumberFormat();
const PAGE = 50;

/** The service reports generated for the company's stores, with search and paging. */
export function ReportLibrary({
  scope,
}: {
  scope: { companyId: string; billToId: string; state: string };
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const library = useDashboardGetReportLibrary(scope.companyId, {
    ...(scope.billToId ? { bill_to_id: scope.billToId } : {}),
    ...(scope.state ? { state: scope.state } : {}),
    ...(query.trim() ? { q: query.trim() } : {}),
    limit: PAGE,
    offset: page * PAGE,
  });
  const data = library.data?.data;
  const pages = data ? Math.ceil(data.total / PAGE) : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Generated Reports</CardTitle>
        <CardDescription>
          Service reports finished in this portal, newest first. Each opens at its current version.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-56 flex-col gap-1">
            <Label htmlFor="library-find">Search</Label>
            <Input
              id="library-find"
              type="search"
              placeholder="Report, store number, or store name"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </div>
          {data && (
            <p className="ml-auto text-sm text-muted-foreground">
              {integer.format(data.total)} reports
            </p>
          )}
        </div>
        {library.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {errorMessage(library.error, "Could not load the reports.")}
            </AlertDescription>
          </Alert>
        )}
        <DataTableFrame>
          <DataTable className="min-w-[640px]">
            <thead>
              <tr>
                <th className="p-3 font-medium">Report</th>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Order</th>
                <th className="p-3 font-medium">Work date</th>
                <th className="p-3 font-medium">Finalized</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {(data?.items ?? []).map((report) => (
                <tr key={report.id} className="align-top">
                  <td className="p-3">
                    <Link
                      href={`/service-reports/${report.id}`}
                      className="text-primary hover:underline"
                    >
                      {report.title}
                    </Link>
                    {report.revision > 1 && (
                      <span className="block text-xs text-muted-foreground">
                        Version {report.revision}
                      </span>
                    )}
                  </td>
                  <td className="p-3 whitespace-nowrap">
                    <StoreLink locationId={report.location_id}>
                      {report.store_number ? `#${report.store_number}` : report.name}
                    </StoreLink>
                  </td>
                  <td className="p-3 whitespace-nowrap">{report.order_number ?? "—"}</td>
                  <td className="p-3 whitespace-nowrap">{day(report.work_date)}</td>
                  <td className="p-3 whitespace-nowrap">{day(report.finalized_on)}</td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-4 text-muted-foreground">
                    No reports match.
                  </td>
                </tr>
              )}
            </tbody>
          </DataTable>
        </DataTableFrame>
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
      </CardContent>
    </Card>
  );
}
