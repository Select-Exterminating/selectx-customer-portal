"use client";

import { ChevronLeft, ChevronRight, Play, X } from "lucide-react";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { useStoreParam, StoreLink } from "@/components/dashboard-link";
import { DataTable, DataTableFrame } from "@/components/data-table";
import { day, Eyebrow, pct } from "@/components/program-overview";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  CeilingReview,
  ConditionReview,
  FrontLineReview,
  RecurrenceDrivers,
  SixMonthReview,
  StoreRef,
} from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

const integer = new Intl.NumberFormat();

const PresentContext = createContext<{ presenting: boolean; current: number }>({
  presenting: false,
  current: 0,
});

/** One block of the review: everything on the page, or one full screen while presenting. */
export function Slide({ n, children }: { n: number; children: ReactNode }) {
  const { presenting, current } = useContext(PresentContext);
  if (presenting && current !== n) return null;
  return <>{children}</>;
}

/** Holds the review's slides and runs present mode: arrow keys or space to move, Esc to leave. */
export function PresentFrame({ count, children }: { count: number; children: ReactNode }) {
  const [presenting, setPresenting] = useState(false);
  const [current, setCurrent] = useState(0);
  const [store] = useStoreParam();
  const frame = useRef<HTMLDivElement>(null);

  const stop = useCallback(() => {
    setPresenting(false);
    if (document.fullscreenElement) {
      document.exitFullscreen().catch((error) => {
        console.error("Could not leave full screen", error);
      });
    }
  }, []);
  const start = () => {
    setCurrent(0);
    setPresenting(true);
    // Present mode works without it: browsers may refuse, and the frame already fills the window.
    frame.current?.requestFullscreen?.().catch((error) => {
      console.error("Could not enter full screen", error);
    });
  };
  const move = useCallback(
    (by: number) => setCurrent((c) => Math.max(0, Math.min(count - 1, c + by))),
    [count],
  );

  useEffect(() => {
    if (!presenting) return;
    const onKey = (e: KeyboardEvent) => {
      // A store's flyover opened from a slide takes the keys while it's up.
      if (store) return;
      if (["ArrowRight", "PageDown", " "].includes(e.key)) {
        e.preventDefault();
        move(1);
      } else if (["ArrowLeft", "PageUp"].includes(e.key)) {
        e.preventDefault();
        move(-1);
      } else if (e.key === "Escape") {
        stop();
      }
    };
    const onFullscreen = () => {
      if (!document.fullscreenElement) setPresenting(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("fullscreenchange", onFullscreen);
    };
  }, [presenting, store, move, stop]);

  return (
    <PresentContext.Provider value={{ presenting, current }}>
      <div
        ref={frame}
        className={cn(
          "flex flex-col gap-8",
          presenting && "fixed inset-0 z-40 overflow-auto bg-background px-6 pt-8 pb-20 sm:px-12",
        )}
      >
        {!presenting && (
          <div className="flex justify-end">
            <Button size="sm" onClick={start}>
              <Play aria-hidden />
              Present
            </Button>
          </div>
        )}
        {children}
        {presenting && (
          <div className="fixed right-4 bottom-4 z-50 flex items-center gap-2 rounded-lg border border-border bg-card p-1.5 shadow-sm">
            <Button
              size="sm"
              variant="ghost"
              aria-label="Previous slide"
              disabled={current === 0}
              onClick={() => move(-1)}
            >
              <ChevronLeft aria-hidden />
            </Button>
            <span className="text-sm tabular-nums" aria-live="polite">
              {current + 1} / {count}
            </span>
            <Button
              size="sm"
              variant="ghost"
              aria-label="Next slide"
              disabled={current === count - 1}
              onClick={() => move(1)}
            >
              <ChevronRight aria-hidden />
            </Button>
            <Button size="sm" variant="ghost" aria-label="Leave present mode" onClick={stop}>
              <X aria-hidden />
            </Button>
          </div>
        )}
      </div>
    </PresentContext.Provider>
  );
}

function Section({
  eyebrow,
  children,
  source,
}: {
  eyebrow: string;
  children: ReactNode;
  source?: string;
}) {
  return (
    <section className="flex flex-col gap-4">
      <Eyebrow>{eyebrow}</Eyebrow>
      {children}
      {source && <p className="text-xs text-muted-foreground">{source}</p>}
    </section>
  );
}

const TILES = "grid gap-3 sm:grid-cols-2 lg:grid-cols-4";

function storeLabel(s: StoreRef) {
  return s.store_number ? `#${s.store_number}` : (s.name ?? "Store");
}

export function Ceilings({ c }: { c: CeilingReview }) {
  return (
    <Section
      eyebrow="The yield · ceilings"
      source="Assessment figures are from each restaurant's latest assessment. The visit share is of service visits with activity."
    >
      <h3 className="text-xl font-bold">Ceilings: The Portfolio-Wide Structural Constant</h3>
      <dl className={TILES}>
        <StatTile
          label="Assessed stores with drop ceilings"
          value={pct(c.stores_assessed ? c.drop_ceilings / c.stores_assessed : null)}
          note={`${integer.format(c.drop_ceilings)} of ${integer.format(c.stores_assessed)}`}
        />
        <StatTile
          label="Ceiling-corridor zones with rodent activity"
          value={pct(c.zone_rodent_rate)}
          note={`${integer.format(c.zone_inspected)} zone inspections`}
        />
        <StatTile
          label="Visits with activity naming a ceiling"
          value={pct(c.activity_visit_share)}
        />
        <StatTile
          label="Assessed stores with a rodent-active zone"
          value={integer.format(c.rodent_zone_stores)}
          note={`of ${integer.format(c.stores_assessed)}`}
        />
      </dl>
    </Section>
  );
}

function FrontLineSide({
  title,
  rate,
  inspected,
  zone,
  share,
  words,
}: {
  title: string;
  rate: number | null;
  inspected: number;
  zone: string;
  share: number | null;
  words: string;
}) {
  return (
    <StatTile
      label={`${title}: zones with rodent activity`}
      value={pct(rate)}
      note={`${integer.format(inspected)} ${zone} inspections · ${pct(share)} of service visits with activity name ${words}`}
    />
  );
}

export function FrontLine({ f }: { f: FrontLineReview }) {
  return (
    <Section
      eyebrow="The yield · the line"
      source="Assessments measure the DML through the Service Line / Food Preparation zone and the front line through Front of House. Visit shares come from the technician's words, so a visit can name both."
    >
      <h3 className="text-xl font-bold">Front Line vs. DML</h3>
      <dl className="grid gap-3 md:grid-cols-2">
        <FrontLineSide
          title="Digital make line"
          rate={f.dml_rodent_rate}
          inspected={f.dml_inspected}
          zone="service line"
          share={f.dml_visit_share}
          words="the service line or DML"
        />
        <FrontLineSide
          title="Front of house"
          rate={f.front_rodent_rate}
          inspected={f.front_inspected}
          zone="front of house"
          share={f.front_visit_share}
          words="the dining room or front line"
        />
      </dl>
    </Section>
  );
}

export function Drivers({ d }: { d: RecurrenceDrivers }) {
  return (
    <Section
      eyebrow="The yield · recurrence"
      source={`Share of the ${integer.format(d.active)} treated stores still in active stabilization showing each driver in the last 90 days. A store can show more than one. The client-reported count covers every store.`}
    >
      <h3 className="text-xl font-bold">What Drives Recurrence?</h3>
      <dl className={TILES}>
        <StatTile
          label="Structural"
          value={pct(d.structural)}
          note="Open structural items or compromised exclusion. Owner: Facilities and Select."
        />
        <StatTile
          label="Operational"
          value={pct(d.operational)}
          note="Sanitation concerns on recent visits. Owner: Operations."
        />
        <StatTile
          label="Environmental and third party"
          value={pct(d.environmental)}
          note="Exterior, trash-area, or shared-tenant activity, or a mall location. Owner: Real Estate and Landlord."
        />
        <StatTile
          label="Client-reported"
          value={integer.format(d.client_reported)}
          note="Stores with an open finding from food safety, EcoLab, or the store team."
        />
      </dl>
    </Section>
  );
}

export function SixMonth({ s }: { s: SixMonthReview }) {
  return (
    <Section
      eyebrow="The operating model · six months on"
      source="Six months counted from a store's first RAMP order. The tracker's Phase 2 dates aren't held here and PestPac's monitoring code only began in June 2026, so counts can differ from the RAMP portal's."
    >
      <h3 className="text-xl font-bold">The Six-Month Question</h3>
      <dl className={TILES}>
        <StatTile
          label="Stores six months past their first RAMP order"
          value={integer.format(s.stores)}
        />
        <StatTile
          label="Stabilized today"
          value={pct(s.stores ? s.stabilized / s.stores : null)}
          note={`${integer.format(s.stabilized)} of ${integer.format(s.stores)}`}
        />
        <StatTile label="With activity after month six" value={integer.format(s.activity_after)} />
        <StatTile
          label="Activity after a service gap"
          value={integer.format(s.gaps_with_activity)}
          note="Activity on the first service after 21+ days without one"
        />
      </dl>
      {s.activity_stores.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
          <span className="font-bold">Stores with activity after month six:</span>
          {s.activity_stores.map((store) => (
            <StoreLink key={store.location_id} locationId={store.location_id}>
              {storeLabel(store)}
            </StoreLink>
          ))}
        </div>
      )}
    </Section>
  );
}

export function ConditionOwnership({ c }: { c: ConditionReview }) {
  return (
    <Section
      eyebrow="The operating model · ownership"
      source="PestPac's condition log, voided conditions left out. Owners are PestPac's responsibility field, so this covers more than the portal's hand-kept log, with coarser owners."
    >
      <h3 className="text-xl font-bold">Reporting Becomes the Communication System</h3>
      <dl className={TILES}>
        <StatTile label="Conditions found" value={integer.format(c.found)} />
        <StatTile
          label="Ownership assigned"
          value={integer.format(c.assigned)}
          note={c.owners.map((o) => `${integer.format(o.visits)} ${o.label}`).join(" · ")}
        />
        <StatTile label="Still open" value={integer.format(c.open)} />
        <StatTile label="Resolved" value={integer.format(c.resolved)} />
      </dl>
      {c.high_open.length > 0 && (
        <DataTableFrame className="max-h-96">
          <DataTable>
            <thead>
              <tr>
                <th className="p-3 font-medium">Store</th>
                <th className="p-3 font-medium">Severity</th>
                <th className="p-3 font-medium">Area</th>
                <th className="p-3 font-medium">Category</th>
                <th className="p-3 font-medium">Owner</th>
                <th className="p-3 font-medium">Opened</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {c.high_open.map((r, i) => (
                <tr key={`${r.location_id}-${i}`}>
                  <td className="p-3">
                    <StoreLink locationId={r.location_id} className="font-medium">
                      {storeLabel(r)}
                    </StoreLink>
                  </td>
                  <td className="p-3">
                    <Badge variant="destructive">{r.severity}</Badge>
                  </td>
                  <td className="p-3">{r.area ?? "—"}</td>
                  <td className="p-3">{r.category ?? "—"}</td>
                  <td className="p-3">{r.owner}</td>
                  <td className="p-3 whitespace-nowrap">{day(r.opened)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </DataTableFrame>
      )}
    </Section>
  );
}
