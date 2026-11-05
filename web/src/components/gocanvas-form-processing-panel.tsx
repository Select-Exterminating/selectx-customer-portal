"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AddDialog } from "@/components/add-dialog";
import { DataTable, DataTableFrame } from "@/components/data-table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { errorMessage } from "@/lib/api/errors";
import {
  getGocanvasListFormProcessingQueryKey,
  useGocanvasClearFormProcessing,
  useGocanvasListFormProcessing,
  useGocanvasSetFormProcessing,
} from "@/lib/api/generated/gocanvas/gocanvas";
import type { GoCanvasProcessing } from "@/lib/api/generated/model";

const PROCESSING: { value: GoCanvasProcessing; label: string }[] = [
  { value: "risk_assessment", label: "Risk Assessment" },
  { value: "ipm_form", label: "IPM Form" },
];

const schema = z.object({
  root: z.coerce
    .number<string | number>()
    .int("Whole number")
    .min(1, "Required")
    .max(Number.MAX_SAFE_INTEGER, "Too large"),
  processing: z.enum(["risk_assessment", "ipm_form"]),
});
type FormInput = z.input<typeof schema>;

function AddRootForm({ operatorId, close }: { operatorId: string; close: () => void }) {
  const queryClient = useQueryClient();
  const save = useGocanvasSetFormProcessing({
    mutation: {
      onSuccess: () =>
        queryClient.invalidateQueries({
          queryKey: getGocanvasListFormProcessingQueryKey(operatorId),
        }),
    },
  });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormInput, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { root: "", processing: "risk_assessment" },
  });
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={handleSubmit(async ({ root, processing }) => {
        await save.mutateAsync({ operatorId, root, data: { processing } });
        close();
      })}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="gc-root-id">Root ID</Label>
        <Input id="gc-root-id" inputMode="numeric" autoComplete="off" {...register("root")} />
        {errors.root && <p className="text-sm text-destructive">{errors.root.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="gc-root-processing">Processing</Label>
        <NativeSelect id="gc-root-processing" {...register("processing")}>
          {PROCESSING.map((p) => (
            <NativeSelectOption key={p.value} value={p.value}>
              {p.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      {save.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(save.error)}</AlertDescription>
        </Alert>
      )}
      <div>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Add"}
        </Button>
      </div>
    </form>
  );
}

/** Which processing runs on a form's submissions, by the root ID all its versions share. */
export function GoCanvasFormProcessingPanel({
  operatorId,
  canWrite,
}: {
  operatorId: string;
  canWrite: boolean;
}) {
  const queryClient = useQueryClient();
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: getGocanvasListFormProcessingQueryKey(operatorId) });
  const list = useGocanvasListFormProcessing(operatorId);
  const save = useGocanvasSetFormProcessing({ mutation: { onSuccess: refresh } });
  const clear = useGocanvasClearFormProcessing({ mutation: { onSuccess: refresh } });
  const busy = save.isPending || clear.isPending;
  const failed = save.error ?? clear.error;
  const rows = list.data?.data.items ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <CardTitle>Form Processing</CardTitle>
          <CardDescription>
            Every submission is stored. Its form&apos;s root ID decides what processes it. A form
            appears here once a submission arrives, or add its root ID ahead of time.
          </CardDescription>
        </div>
        {canWrite && (
          <AddDialog
            label="Add Root ID"
            title="Add a form root ID"
            description="The root_version_id GoCanvas gives the form."
          >
            {(close) => <AddRootForm operatorId={operatorId} close={close} />}
          </AddDialog>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {list.isPending && <p className="text-muted-foreground">Loading…</p>}
        {list.isError && (
          <Alert variant="destructive">
            <AlertDescription>
              {errorMessage(list.error, "Could not load form processing.")}
            </AlertDescription>
          </Alert>
        )}
        {failed && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(failed)}</AlertDescription>
          </Alert>
        )}
        {list.isSuccess && rows.length === 0 && (
          <p className="text-sm text-muted-foreground">No forms yet.</p>
        )}
        {rows.length > 0 && (
          <DataTableFrame>
            <DataTable>
              <thead>
                <tr>
                  <th scope="col">Root ID</th>
                  <th scope="col">Form</th>
                  <th scope="col">Processing</th>
                  <th scope="col" className="text-right">
                    Submissions
                  </th>
                  <th scope="col" className="text-right">
                    Not processed
                  </th>
                  {canWrite && <th scope="col" aria-label="Actions" />}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const root = row.root_version_id;
                  const label = PROCESSING.find((p) => p.value === row.processing)?.label;
                  return (
                    <tr key={root}>
                      <td className="font-medium">{root}</td>
                      <td>
                        {row.form_name ?? (
                          <span className="text-muted-foreground">No submissions yet</span>
                        )}
                      </td>
                      <td>
                        {canWrite ? (
                          <NativeSelect
                            aria-label={`Processing for root ID ${root}`}
                            value={row.processing ?? ""}
                            disabled={busy}
                            onChange={(e) => {
                              const value = e.target.value as GoCanvasProcessing | "";
                              if (value) {
                                save.mutate({ operatorId, root, data: { processing: value } });
                              } else {
                                clear.mutate({ operatorId, root });
                              }
                            }}
                          >
                            <NativeSelectOption value="">None (store only)</NativeSelectOption>
                            {PROCESSING.map((p) => (
                              <NativeSelectOption key={p.value} value={p.value}>
                                {p.label}
                              </NativeSelectOption>
                            ))}
                          </NativeSelect>
                        ) : (
                          (label ?? (
                            <span className="text-muted-foreground">None (store only)</span>
                          ))
                        )}
                      </td>
                      <td className="text-right">{row.submission_count.toLocaleString()}</td>
                      <td className="text-right">{row.unprocessed_count.toLocaleString()}</td>
                      {canWrite && (
                        <td className="text-right">
                          {row.processing && !row.form_name && (
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Remove root ID ${root}`}
                              disabled={busy}
                              onClick={() => clear.mutate({ operatorId, root })}
                            >
                              <Trash2 aria-hidden />
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </DataTable>
          </DataTableFrame>
        )}
      </CardContent>
    </Card>
  );
}
