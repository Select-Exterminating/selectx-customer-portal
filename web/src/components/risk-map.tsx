"use client";

import {
  type ExtendedFeatureCollection,
  type GeoGeometryObjects,
  geoMercator,
  geoPath,
} from "d3-geo";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { feature } from "topojson-client";

import type { StoreWatchRow } from "@/lib/api/generated/model";

const WIDTH = 640;
const MIN_HEIGHT = 320;
const MAX_HEIGHT = 520;
const PAD = 24;
// Draw the riskiest stores last, so they sit on top.
const BAND_ORDER: Record<string, number> = {
  "No Service Data": 0,
  "Not Scored": 0,
  Controlled: 1,
  Low: 1,
  Elevated: 2,
  Moderate: 2,
  High: 3,
  Critical: 4,
};

/** What a dot needs. `services` is left out of a map of stores that aren't all serviced. */
type MapStore = Pick<
  StoreWatchRow,
  "location_id" | "store_number" | "name" | "city" | "latitude" | "longitude" | "risk_band"
> & { risk_index?: number | null; attention?: string; services?: number };

type States = ExtendedFeatureCollection<{
  type: "Feature";
  geometry: GeoGeometryObjects;
  properties: { name: string };
}>;
type Topology = Parameters<typeof feature>[0];

/** US state outlines (us-atlas, from the Census Bureau's cartographic boundaries), loaded on
 * first use so they stay out of the page bundle. */
function useStates(): { states: States | null; failed: boolean } {
  const [states, setStates] = useState<States | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    import("us-atlas/states-10m.json")
      .then((mod) => {
        const topology = (mod.default ?? mod) as unknown as Topology;
        if (live) setStates(feature(topology, topology.objects.states) as unknown as States);
      })
      .catch((error: unknown) => {
        console.error("Could not load the state outlines", error);
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, []);
  return { states, failed };
}

/** Coordinates in or near the US. PestPac holds some that aren't (0,0, one in Australia), and one of
 * those would zoom the map out to the whole world. */
function onUsMap(s: MapStore) {
  const { latitude: lat, longitude: lng } = s;
  return lat !== null && lng !== null && lat > 18 && lat < 72 && lng > -170 && lng < -60;
}

/** One dot per store, colored by its risk band, on state outlines fitted to the serviced stores (or
 * to them all, when none is), as tall as they need so the map fills its card. Clicking a dot opens
 * the store's page, or does `onSelect` instead. */
export function RiskMap({
  stores,
  bandColor,
  onSelect,
}: {
  stores: MapStore[];
  bandColor: Record<string, string>;
  onSelect?: (locationId: string) => void;
}) {
  const router = useRouter();
  const { states, failed } = useStates();
  const points = useMemo(
    () =>
      stores
        .filter(onUsMap)
        .sort((a, b) => (BAND_ORDER[a.risk_band] ?? 0) - (BAND_ORDER[b.risk_band] ?? 0)),
    [stores],
  );
  const unmapped = stores.filter((s) => !onUsMap(s));
  const { projection, height } = useMemo(() => {
    if (points.length === 0) return { projection: null, height: MIN_HEIGHT };
    const serviced = points.filter((s) => (s.services ?? 1) > 0);
    const multipoint: GeoGeometryObjects = {
      type: "MultiPoint",
      coordinates: (serviced.length > 0 ? serviced : points).map((s) => [
        s.longitude!,
        s.latitude!,
      ]),
    };
    const [[, top], [, bottom]] = geoPath(
      geoMercator().fitWidth(WIDTH - 2 * PAD, multipoint),
    ).bounds(multipoint);
    const height = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, bottom - top + 2 * PAD));
    return {
      projection: geoMercator().fitExtent(
        [
          [PAD, PAD],
          [WIDTH - PAD, height - PAD],
        ],
        multipoint,
      ),
      height,
    };
  }, [points]);

  if (!projection) {
    return <p className="text-sm text-muted-foreground">No stores with map coordinates.</p>;
  }
  const path = geoPath(projection);
  return (
    <>
      {failed && (
        <p className="text-sm text-muted-foreground">State outlines could not be loaded.</p>
      )}
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Map of ${points.length} stores colored by risk band`}
      >
        <defs>
          <clipPath id="risk-map-clip">
            <rect width={WIDTH} height={height} />
          </clipPath>
        </defs>
        <rect width={WIDTH} height={height} fill="var(--background)" />
        <g clipPath="url(#risk-map-clip)">
          {states?.features.map((f) => (
            <path
              key={f.properties.name}
              d={path(f) ?? undefined}
              fill="var(--muted)"
              stroke="var(--border)"
              strokeWidth={1}
            />
          ))}
        </g>
        {points.map((s) => {
          const [x, y] = projection([s.longitude!, s.latitude!]) ?? [0, 0];
          return (
            <circle
              key={s.location_id}
              cx={x}
              cy={y}
              r={5}
              fill={bandColor[s.risk_band] ?? "var(--border)"}
              stroke="var(--background)"
              strokeWidth={1.2}
              className="cursor-pointer"
              onClick={() =>
                onSelect ? onSelect(s.location_id) : router.push(`/locations/${s.location_id}`)
              }
            >
              <title>
                {[
                  s.store_number ? `#${s.store_number}` : s.name,
                  s.city,
                  `${s.risk_band}${s.risk_index == null ? "" : ` (${s.risk_index})`}`,
                  s.attention,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </title>
            </circle>
          );
        })}
      </svg>
      {unmapped.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Not on the map because their location details need correcting:{" "}
          {unmapped.map((s) => (s.store_number ? `#${s.store_number}` : s.name)).join(", ")}.
        </p>
      )}
    </>
  );
}
