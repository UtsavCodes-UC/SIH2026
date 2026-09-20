import L from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { GraphView, LatLng, OptimizeResponse, ShortestPathResponse } from "../api/types";
import { CONGESTION_BUCKETS, PATH_COLORS, bucketIndex, coordinateIndex, vehicleColor } from "../lib/helpers";
import TrafficBadge from "./TrafficBadge";

export type SelectMode = "off" | "depot" | "stops" | "pathA" | "pathB";

interface Props {
  graph: GraphView;
  depot: number | null;
  stops: number[];
  demands: Record<string, number> | null;
  result: OptimizeResponse | null;
  pathA: number | null;
  pathB: number | null;
  pathResult: ShortestPathResponse | null; // drawn instead of the vehicle routes when given
  selectMode: SelectMode;
  onPickNode: (id: number) => void;
  onSelectMode: (mode: SelectMode) => void;
}

function FitBounds({ bounds, graphId }: { bounds: [LatLng, LatLng]; graphId: string }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [24, 24] });
    // refit only when a different network is loaded, not when its congestion changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId, map]);
  return null;
}

/** Picks the node nearest a map click (within 20 px) while a selection mode is active. */
function ClickPicker({ nodes, mode, onPick }: { nodes: GraphView["nodes"]; mode: SelectMode; onPick: (id: number) => void }) {
  const map = useMap();
  useEffect(() => {
    map.getContainer().style.cursor = mode === "off" ? "" : "crosshair";
  }, [map, mode]);

  useMapEvents({
    click(event) {
      if (mode === "off") return;
      const target = map.latLngToContainerPoint(event.latlng);
      let best = -1;
      let bestDistance = Infinity;
      for (const [id, lat, lon] of nodes) {
        const point = map.latLngToContainerPoint([lat, lon]);
        const d = (point.x - target.x) ** 2 + (point.y - target.y) ** 2;
        if (d < bestDistance) {
          bestDistance = d;
          best = id;
        }
      }
      if (best !== -1 && bestDistance <= 20 * 20) onPick(best);
    },
  });
  return null;
}

const badgeIcon = (label: string, color: string) =>
  L.divIcon({
    className: "",
    html: `<div class="stop-badge" style="background:${color}">${label}</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });

const depotIcon = L.divIcon({
  className: "",
  html: `<div class="depot-badge">D</div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

const endpointIcon = (label: string) =>
  L.divIcon({
    className: "",
    html: `<div class="endpoint-badge">${label}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });

export default function MapView({ graph, depot, stops, demands, result, pathA, pathB, pathResult, selectMode, onPickNode, onSelectMode }: Props) {
  const coords = useMemo(() => coordinateIndex(graph.nodes), [graph.nodes]);

  // Roads grouped by congestion band: a handful of multi-polylines instead of thousands of layers.
  const roadBands = useMemo(() => {
    const bands: LatLng[][][] = CONGESTION_BUCKETS.map(() => []);
    for (const [u, v, congestion] of graph.edges) {
      const a = coords.get(u);
      const b = coords.get(v);
      if (a && b) bands[bucketIndex(congestion)].push([a, b]);
    }
    return bands;
  }, [graph.edges, coords]);

  const showAllNodes = selectMode !== "off" || graph.nodes.length <= 150;
  const stopSet = useMemo(() => new Set(stops), [stops]);
  const solved = result !== null;

  return (
    <div className="map-wrap">
      <MapContainer bounds={graph.summary.bounds} preferCanvas zoomSnap={0.25} className="map" zoomControl>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          opacity={0.55}
        />
        <FitBounds bounds={graph.summary.bounds} graphId={graph.summary.graph_id} />
        <ClickPicker nodes={graph.nodes} mode={selectMode} onPick={onPickNode} />

        {roadBands.map((lines, i) =>
          lines.length ? (
            <Polyline
              key={`band-${i}`}
              positions={lines}
              interactive={false}
              pathOptions={{ color: CONGESTION_BUCKETS[i].color, weight: CONGESTION_BUCKETS[i].weight, opacity: 0.85 }}
            />
          ) : null,
        )}

        {showAllNodes &&
          graph.nodes.map(([id, lat, lon]) =>
            id === depot || stopSet.has(id) ? null : (
              <CircleMarker
                key={id}
                center={[lat, lon]}
                radius={selectMode !== "off" && graph.nodes.length <= 300 ? 3.5 : 2.5}
                interactive={false}
                pathOptions={{ color: "#5b6673", weight: 1, fillColor: "#ffffff", fillOpacity: 1 }}
              />
            ),
          )}

        {/* shortest path: the exact route underneath, each search a thinner line on top of it */}
        {pathResult?.results
          .slice()
          .sort((a, b) => Number(b.algorithm === "dijkstra") - Number(a.algorithm === "dijkstra"))
          .map((r) => (
            <Polyline
              key={`path-${r.algorithm}`}
              positions={r.path}
              interactive={false}
              pathOptions={{ color: PATH_COLORS[r.algorithm], weight: r.algorithm === "dijkstra" ? 8 : 4, opacity: r.algorithm === "dijkstra" ? 0.9 : 1, dashArray: r.algorithm === "dijkstra" ? undefined : "1 7", lineCap: "round" }}
            />
          ))}

        {result?.routes.map((route) => (
          <Polyline
            key={`casing-${route.vehicle}`}
            positions={route.path}
            interactive={false}
            pathOptions={{ color: "#ffffff", weight: 9, opacity: 0.95 }}
          />
        ))}
        {result?.routes.map((route) => (
          <Polyline
            key={`route-${route.vehicle}`}
            positions={route.path}
            interactive={false}
            pathOptions={{ color: vehicleColor(route.vehicle - 1), weight: 5, opacity: 1 }}
          />
        ))}

        {/* Before solving: selected stops as plain dots. After: numbered badges in visiting order. */}
        {!solved &&
          stops.map((id) => {
            const position = coords.get(id);
            return position ? (
              <CircleMarker
                key={`stop-${id}`}
                center={position}
                radius={7}
                pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#1f2937", fillOpacity: 1 }}
              >
                <Tooltip>{demands?.[String(id)] !== undefined ? `Stop ${id} · demand ${demands[String(id)]}` : `Stop ${id}`}</Tooltip>
              </CircleMarker>
            ) : null;
          })}

        {result?.routes.flatMap((route) =>
          route.nodes.slice(1, -1).map((id, index) => {
            const position = coords.get(id);
            return position ? (
              <Marker key={`badge-${route.vehicle}-${id}`} position={position} icon={badgeIcon(String(index + 1), vehicleColor(route.vehicle - 1))}>
                <Tooltip>{`Vehicle ${route.vehicle}, stop ${index + 1} · node ${id} · demand ${result.problem.demands[String(id)] ?? "?"}`}</Tooltip>
              </Marker>
            ) : null;
          }),
        )}

        {[["A", pathA], ["B", pathB]].map(([label, id]) => {
          const position = id === null ? undefined : coords.get(id as number);
          return position ? (
            <Marker key={`end-${label}`} position={position} icon={endpointIcon(label as string)} zIndexOffset={900}>
              <Tooltip>{`${label} · node ${id}`}</Tooltip>
            </Marker>
          ) : null;
        })}

        {depot !== null && coords.get(depot) && (
          <Marker position={coords.get(depot)!} icon={depotIcon} zIndexOffset={1000}>
            <Tooltip>{`Depot · node ${depot}`}</Tooltip>
          </Marker>
        )}
      </MapContainer>

      <div className="map-toolbar" role="group" aria-label="Pick locations on the map">
        <span className="map-toolbar-label">Click the map to</span>
        {(
          [
            ["depot", "set depot"],
            ["stops", "toggle stops"],
            ["pathA", "set A"],
            ["pathB", "set B"],
          ] as const
        ).map(([mode, label]) => (
          <button
            key={mode}
            className={selectMode === mode ? "chip chip-active" : "chip"}
            onClick={() => onSelectMode(selectMode === mode ? "off" : mode)}
            aria-pressed={selectMode === mode}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="map-badge">
        <TrafficBadge info={graph.summary.traffic} />
      </div>

      <div className="map-legend" aria-label="Traffic legend">
        <strong>Traffic</strong>
        {CONGESTION_BUCKETS.map((b) => (
          <span key={b.label} className="legend-item">
            <i style={{ background: b.color }} />
            {b.label}
          </span>
        ))}
      </div>
    </div>
  );
}
