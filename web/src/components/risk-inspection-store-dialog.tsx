"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { RiskInspectionDetail, StoreCandidate } from "@/lib/api/generated/model";
import {
  useRiskInspectionsSearchRiskInspectionStores,
  useRiskInspectionsSetRiskInspectionLocation,
} from "@/lib/api/generated/risk-inspections/risk-inspections";

const place = (s: StoreCandidate) => [s.address, s.city, s.state].filter(Boolean).join(", ");

/** Finds a store and links the inspection to it, after naming what the choice changes. */
export function RiskInspectionStoreDialog({ report }: { report: RiskInspectionDetail }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<StoreCandidate | null>(null);
  const q = useDeferredValue(query.trim());
  const queryClient = useQueryClient();

  const stores = useRiskInspectionsSearchRiskInspectionStores(
    report.id,
    { q },
    { query: { enabled: open && q.length > 0 } },
  );
  const link = useRiskInspectionsSetRiskInspectionLocation({
    mutation: {
      onSuccess: async () => {
        // The inspection moves between lists, on pages this one can't name.
        await queryClient.invalidateQueries();
        setOpen(false);
      },
    },
  });

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    setQuery("");
    setChosen(null);
    link.reset();
  };
  const verb = report.location_id ? "Change Store" : "Link to Store";
  const results = stores.data?.data ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger
        render={<Button size="sm" variant={report.location_id ? "outline" : "default"} />}
      >
        {verb}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{verb}</DialogTitle>
          <DialogDescription>
            The store decides which customer can see this inspection and its photos.
          </DialogDescription>
        </DialogHeader>

        {chosen ? (
          <div className="flex flex-col gap-3">
            {report.location_id ? (
              <p>
                Move this inspection from <strong>{report.location_name}</strong>
                {report.company_name && ` (${report.company_name})`} to{" "}
                <strong>{chosen.name}</strong>
                {chosen.company_name && ` (${chosen.company_name})`}?
              </p>
            ) : (
              <p>
                Link this inspection to <strong>{chosen.name}</strong>
                {chosen.company_name && ` (${chosen.company_name})`}?
              </p>
            )}
            <p className="text-sm text-muted-foreground">{place(chosen)}</p>
            <p className="text-sm text-muted-foreground">
              Automatic linking won&apos;t change a store chosen here.
            </p>
            {link.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(link.error, "Could not link the store.")}
                </AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button variant="outline" disabled={link.isPending} onClick={() => setChosen(null)}>
                Back
              </Button>
              <Button
                disabled={link.isPending}
                onClick={() =>
                  link.mutate({ inspectionId: report.id, data: { location_id: chosen.id } })
                }
              >
                {verb}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="store-search">Search stores</Label>
              <Input
                id="store-search"
                autoFocus
                value={query}
                maxLength={200}
                placeholder="Customer, store number, address, or city"
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <p className="text-sm text-muted-foreground">
              The form says:{" "}
              {[report.store_label, report.address, report.city, report.work_order_ref]
                .filter(Boolean)
                .join(" · ") || "nothing about the store"}
            </p>
            {stores.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(stores.error, "Could not search stores.")}
                </AlertDescription>
              </Alert>
            )}
            {q && stores.isSuccess && results.length === 0 && (
              <p className="text-muted-foreground">No stores match.</p>
            )}
            {results.length > 0 && (
              <ul className="flex max-h-72 flex-col divide-y divide-border overflow-auto rounded-lg border border-border">
                {results.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setChosen(s)}
                      className="flex w-full cursor-pointer flex-col px-3 py-2 text-left hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      <span className="font-medium">
                        {s.name}
                        {s.description && ` · ${s.description}`}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {[s.company_name, place(s)].filter(Boolean).join(" · ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
