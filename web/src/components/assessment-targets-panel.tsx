"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDashboardGetAssessmentTargets,
  useDashboardPutAssessmentTargets,
} from "@/lib/api/generated/dashboard/dashboard";
import { errorMessage } from "@/lib/api/errors";

const schema = z.object({
  targets: z
    .array(
      z.object({
        state: z
          .string()
          .trim()
          .toUpperCase()
          .regex(/^[A-Z]{2}$/, "Two letters"),
        total: z.coerce
          .number<string | number>()
          .int("Whole number")
          .min(0, "0 or more")
          .max(100000, "Too large"),
      }),
    )
    .refine((rows) => new Set(rows.map((r) => r.state)).size === rows.length, {
      message: "A state is listed twice.",
    }),
});
type Form = z.input<typeof schema>;

/** How many restaurants in each state the company's risk assessments cover. */
export function AssessmentTargetsPanel({
  companyId,
  canWrite,
}: {
  companyId: string;
  canWrite: boolean;
}) {
  const queryClient = useQueryClient();
  const query = useDashboardGetAssessmentTargets(companyId);
  const save = useDashboardPutAssessmentTargets({
    mutation: { onSuccess: () => queryClient.invalidateQueries() },
  });
  const form = useForm<Form, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { targets: [] },
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "targets" });
  const saved = query.data?.data.targets;
  useEffect(() => {
    if (saved) form.reset({ targets: saved });
  }, [saved, form]);

  if (query.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {errorMessage(query.error, "Could not load the assessment targets.")}
        </AlertDescription>
      </Alert>
    );
  }
  const errors = form.formState.errors.targets;
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Assessment Targets</CardTitle>
        <CardDescription>
          How many restaurants in each state the risk assessments cover. The dashboard&apos;s
          coverage counts against these; a state without one counts against our locations there.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3"
          onSubmit={form.handleSubmit((values) => save.mutate({ companyId, data: values }))}
        >
          {fields.length === 0 && <p className="text-sm text-muted-foreground">No targets set.</p>}
          {fields.map((field, i) => (
            <div key={field.id} className="grid grid-cols-[6rem_8rem_auto] items-start gap-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor={`target-state-${i}`}>State</Label>
                <Input
                  id={`target-state-${i}`}
                  maxLength={2}
                  disabled={!canWrite}
                  aria-invalid={!!errors?.[i]?.state}
                  {...form.register(`targets.${i}.state`)}
                />
                {errors?.[i]?.state && (
                  <p className="text-xs text-destructive">{errors[i].state.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`target-total-${i}`}>Restaurants</Label>
                <Input
                  id={`target-total-${i}`}
                  type="number"
                  min={0}
                  disabled={!canWrite}
                  aria-invalid={!!errors?.[i]?.total}
                  {...form.register(`targets.${i}.total`)}
                />
                {errors?.[i]?.total && (
                  <p className="text-xs text-destructive">{errors[i].total.message}</p>
                )}
              </div>
              {canWrite && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-5"
                  aria-label={`Remove target ${i + 1}`}
                  onClick={() => remove(i)}
                >
                  <Trash2 aria-hidden />
                </Button>
              )}
            </div>
          ))}
          {errors?.root?.message && (
            <p className="text-sm text-destructive">{errors.root.message}</p>
          )}
          {save.isError && (
            <Alert variant="destructive">
              <AlertDescription>
                {errorMessage(save.error, "Could not save the targets.")}
              </AlertDescription>
            </Alert>
          )}
          {save.isSuccess && !form.formState.isDirty && (
            <p className="text-sm text-muted-foreground">Saved.</p>
          )}
          {canWrite && (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => append({ state: "", total: 0 })}
              >
                <Plus aria-hidden />
                Add State
              </Button>
              <Button type="submit" size="sm" disabled={save.isPending}>
                Save
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
