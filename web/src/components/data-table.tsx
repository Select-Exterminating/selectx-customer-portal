import { cn } from "@/lib/utils";

/**
 * The app's data table: a charcoal header row that stays in view, striped rows, 12px text, and
 * tabular numbers. Columns and cells are plain `th` and `td`; alignment stays with each cell.
 */
export function DataTable({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <table
      className={cn(
        "w-full border-collapse text-left text-xs tabular-nums",
        "[&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-1 [&_thead_th]:bg-secondary [&_thead_th]:px-2.5 [&_thead_th]:py-2 [&_thead_th]:font-bold [&_thead_th]:whitespace-nowrap [&_thead_th]:text-secondary-foreground",
        "[&_thead_button]:text-secondary-foreground",
        "[&_tbody_td]:px-2.5 [&_tbody_td]:py-2 [&_tbody_th]:px-2.5 [&_tbody_th]:py-2",
        "[&_tbody_tr]:border-b [&_tbody_tr]:border-border [&_tbody_tr:last-child]:border-0 [&_tbody_tr:nth-child(even)]:bg-row",
        className,
      )}
      {...props}
    />
  );
}

/** The frame around a data table. Pass a `max-h-*` to scroll under the sticky header. */
export function DataTableFrame({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("overflow-auto rounded-lg border border-border bg-card", className)}
      {...props}
    />
  );
}
