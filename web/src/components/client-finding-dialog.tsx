"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useAreaMappingListZones } from "@/lib/api/generated/area-mapping/area-mapping";
import {
  useClientFindingsLogClientFinding,
  useClientFindingsUpdateClientFinding,
} from "@/lib/api/generated/client-findings/client-findings";
import { errorMessage } from "@/lib/api/errors";
import type { ClientFindingRead, Zone } from "@/lib/api/generated/model";

const schema = z.object({
  reported_on: z.string(),
  source: z.string().trim().min(1, "Who reported it").max(100),
  finding: z.string().trim().min(1, "What they found").max(4000),
  zone: z.string(),
  severity: z.enum(["low", "medium", "high"]),
  status: z.enum(["open", "closed"]),
  select_response: z.string().trim().max(4000),
});
type Form = z.infer<typeof schema>;

/** Logs what a customer's own people found at a store, or edits and closes one logged already. */
export function ClientFindingDialog({
  locationId,
  operatorId,
  finding,
}: {
  locationId: string;
  operatorId: string;
  finding?: ClientFindingRead;
}) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const zones = useAreaMappingListZones(operatorId, { query: { enabled: open } });
  const values: Form = {
    reported_on: finding?.reported_on ?? "",
    source: finding?.source ?? "",
    finding: finding?.finding ?? "",
    zone: finding?.zone ?? "",
    severity: (finding?.severity as Form["severity"]) ?? "medium",
    status: (finding?.status as Form["status"]) ?? "open",
    select_response: finding?.select_response ?? "",
  };
  const form = useForm<Form>({ resolver: zodResolver(schema), values });
  const done = {
    mutation: {
      onSuccess: async () => {
        await queryClient.invalidateQueries();
        setOpen(false);
      },
    },
  };
  const log = useClientFindingsLogClientFinding(done);
  const update = useClientFindingsUpdateClientFinding(done);
  const save = finding ? update : log;
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((v) => {
    const data = {
      ...v,
      reported_on: v.reported_on || null,
      zone: (v.zone || null) as Zone | null,
      select_response: v.select_response || null,
    };
    if (finding) update.mutate({ findingId: finding.id, data });
    else log.mutate({ locationId, data });
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        form.reset(values);
        log.reset();
        update.reset();
      }}
    >
      <DialogTrigger render={<Button size="sm" variant={finding ? "ghost" : "outline"} />}>
        {finding ? "Edit" : "Log Finding"}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{finding ? "Edit Finding" : "Log Client Finding"}</DialogTitle>
          <DialogDescription>
            What the customer&apos;s own people found and told Select. While it&apos;s open, for 60
            days after it&apos;s logged, it escalates the store in Store Watch. The customer sees
            this.
          </DialogDescription>
        </DialogHeader>
        {/* The zone choices come first, so a saved zone has an option to select when editing. */}
        {zones.isPending && <p className="text-muted-foreground">Loading…</p>}
        {zones.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {errorMessage(zones.error, "Could not load the zones.")}
            </AlertDescription>
          </Alert>
        )}
        {zones.isSuccess && (
          <form className="flex flex-col gap-3" onSubmit={onSubmit}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-source">Source</Label>
                <Input
                  id="cf-source"
                  placeholder="Food safety manager walk"
                  aria-invalid={!!errors.source}
                  {...form.register("source")}
                />
                {errors.source && (
                  <p className="text-xs text-destructive">{errors.source.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-date">Date found</Label>
                <Input id="cf-date" type="date" {...form.register("reported_on")} />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cf-finding">Finding</Label>
              <Textarea
                id="cf-finding"
                aria-invalid={!!errors.finding}
                {...form.register("finding")}
              />
              {errors.finding && (
                <p className="text-xs text-destructive">{errors.finding.message}</p>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-zone">Zone</Label>
                <NativeSelect id="cf-zone" {...form.register("zone")}>
                  <NativeSelectOption value="">Not specified</NativeSelectOption>
                  {zones.data?.data.map((z) => (
                    <NativeSelectOption key={z.zone} value={z.zone}>
                      {z.display_name}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-severity">Severity</Label>
                <NativeSelect id="cf-severity" {...form.register("severity")}>
                  <NativeSelectOption value="low">Low</NativeSelectOption>
                  <NativeSelectOption value="medium">Medium</NativeSelectOption>
                  <NativeSelectOption value="high">High</NativeSelectOption>
                </NativeSelect>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cf-status">Status</Label>
                <NativeSelect id="cf-status" {...form.register("status")}>
                  <NativeSelectOption value="open">Open</NativeSelectOption>
                  <NativeSelectOption value="closed">Closed</NativeSelectOption>
                </NativeSelect>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cf-response">Select&apos;s response</Label>
              <Textarea id="cf-response" {...form.register("select_response")} />
            </div>
            {save.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  {errorMessage(save.error, "Could not save the finding.")}
                </AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button type="submit" disabled={save.isPending}>
                {finding ? "Save" : "Log Finding"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
