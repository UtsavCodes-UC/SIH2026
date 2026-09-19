import type { TrafficInfo, TrafficKind } from "../api/types";
import { formatCaptured } from "../lib/helpers";

const HEADLINE: Record<TrafficKind, string> = {
  live: "LIVE",
  recorded: "RECORDED",
  simulated: "SIMULATED",
  free_flow: "FREE FLOW",
};

const EXPLANATION: Record<TrafficKind, string> = {
  live: "Real readings taken just now. Roads without a reading are estimated from nearby measured roads.",
  recorded: "A recording of real traffic, replayed from disk. It is not happening now.",
  simulated: "Made-up traffic for testing. This is not real data.",
  free_flow: "No congestion applied: every road at its free-flow speed.",
};

/** Says where the congestion on the map comes from. Simulated or recorded traffic must never look live. */
export default function TrafficBadge({ info, inline = false }: { info: TrafficInfo; inline?: boolean }) {
  const real = info.kind === "live" || info.kind === "recorded";
  const details: string[] = [];
  if (real) {
    if (info.provider) details.push(info.provider);
    if (info.captured_at) details.push(formatCaptured(info.captured_at));
    if (info.roads_measured !== null) details.push(`${info.roads_measured} of ${info.roads_total} roads measured`);
    if (info.cached) details.push("recent reading reused");
  } else if (info.kind === "simulated") {
    details.push(info.label);
  }

  return (
    <div className={`traffic-badge traffic-${info.kind}${inline ? " inline" : ""}`} role="status" title={EXPLANATION[info.kind]}>
      <span className="dot" aria-hidden />
      <strong>{HEADLINE[info.kind]}</strong>
      {details.length > 0 && <span>{details.join(" · ")}</span>}
      {real && info.provider === "TomTom" && <span className="credit">Traffic data © TomTom</span>}
    </div>
  );
}
