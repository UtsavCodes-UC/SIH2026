import type { ReactNode } from "react";
import type { TrafficInfo } from "../api/types";
import TrafficBadge from "./TrafficBadge";

interface Props {
  onClose: () => void;
}

const SECTIONS = [
  ["guide-start", "Quick start"],
  ["guide-map", "Reading the map"],
  ["guide-network", "Road network"],
  ["guide-problem", "Delivery problem"],
  ["guide-solver", "Solver"],
  ["guide-results", "Reading the results"],
  ["guide-traffic", "Traffic"],
  ["guide-closures", "Road closures"],
  ["guide-path", "Shortest path"],
  ["guide-panels", "Toolbar and panels"],
  ["guide-notes", "Good to know"],
] as const;

const base = { provider: null, captured_at: null, roads_measured: null, roads_total: 0, cached: false };
const BADGES: { info: TrafficInfo; text: string }[] = [
  { info: { ...base, kind: "live", label: "TomTom", provider: "TomTom", roads_measured: 541, roads_total: 1223 }, text: "Real traffic fetched just now. Roads nobody measured are estimated from their neighbours." },
  { info: { ...base, kind: "recorded", label: "TomTom", provider: "TomTom", captured_at: "2026-09-19T12:53:06+00:00", roads_measured: 541, roads_total: 1223 }, text: "A recording of real traffic, played back. It is not happening now, and it is never shown as live." },
  { info: { ...base, kind: "simulated", label: "rush hour" }, text: "Made-up traffic for testing (random or rush hour)." },
  { info: { ...base, kind: "free_flow", label: "free flow" }, text: "No traffic at all: every road at its full speed." },
];

function Figure({ src, alt, caption, narrow = false }: { src: string; alt: string; caption: ReactNode; narrow?: boolean }) {
  return (
    <figure className={narrow ? "guide-fig narrow" : "guide-fig"}>
      <img src={`/guide/${src}.webp`} alt={alt} loading="lazy" />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

function jump(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function AboutPanel({ onClose }: Props) {
  return (
    <div className="about-backdrop" onClick={onClose}>
      <div className="about-panel" role="dialog" aria-label="Guide" onClick={(e) => e.stopPropagation()}>
        <div className="about-header">
          <h2>Guide</h2>
          <button className="about-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="about-body">
          <div className="guide-content">
            <nav className="guide-nav" aria-label="Guide sections">
              {SECTIONS.map(([id, label]) => (
                <button key={id} type="button" className="chip" onClick={() => jump(id)}>
                  {label}
                </button>
              ))}
            </nav>

            <section id="guide-start">
              <h3>Quick start</h3>
              <p>
                This app plans delivery routes for a fleet of vans over a road network, and lets you see how traffic and closed roads change the plan.
                Three steps get you a first result:
              </p>
              <ol className="guide-steps">
                <li>
                  <strong>Pick a map</strong> (section 01). <em>Synthetic</em> makes a made-up city in one click. <em>Real city</em> loads real streets.
                </li>
                <li>
                  <strong>Choose the stops</strong> (section 02). Press <strong>Draw</strong> to place random delivery stops, or click them on the map.
                </li>
                <li>
                  <strong>Press Optimize routes</strong> (section 03). Each van's route is drawn on the map and explained in the panel at the bottom.
                </li>
              </ol>
              <p>Then experiment: change the traffic (04), close a road, or find the quickest way between two points (05).</p>
              <Figure
                src="overview"
                alt="The whole app with four numbered areas"
                caption={
                  <>
                    <strong>1</strong> the sidebar, where you set things up (sections 01 to 05). <strong>2</strong> the map toolbar: press a button, then click the
                    map. <strong>3</strong> the map, with roads coloured by traffic and the routes on top. <strong>4</strong> the results panel, with three tabs.
                  </>
                }
              />
            </section>

            <section id="guide-map">
              <h3>Reading the map</h3>
              <ul>
                <li>
                  <strong>Road colours</strong> show traffic: grey is free flow, yellow is busy, orange is slow, red is jammed. The legend is at the bottom left of the map.
                </li>
                <li>
                  <strong>D</strong> (black square) is the depot, where every van starts and ends.
                </li>
                <li>
                  <strong>Numbered circles</strong> are the delivery stops, numbered in the order a van visits them. Each van has its own colour. Before you press
                  Optimize, stops are plain dark dots.
                </li>
                <li>
                  <strong>The badge at the top right</strong> says where the traffic comes from (see Traffic below).
                </li>
              </ul>
            </section>

            <section id="guide-network">
              <h3>01 · Road network</h3>
              <p>
                <strong>Synthetic</strong> generates a fake city. <em>Intersections</em> is how many junctions it has, <em>Area</em> is how wide it is in
                kilometres, and <em>Seed</em> is a number that lets you get the same map again. Press <strong>Generate network</strong> to build it.
              </p>
              <p>
                <strong>Real city</strong> uses real streets from OpenStreetMap. Pick one of the ready-made places, or choose <em>Search for another place</em> and start
                typing. <em>Radius</em> is how far from the centre to load, in metres. Press <strong>Load road network</strong>. The first time a place is downloaded
                it can take a minute or two; after that it loads in seconds, even without internet.
              </p>
            </section>

            <section id="guide-problem">
              <h3>02 · Delivery problem</h3>
              <ul>
                <li>
                  <strong>Depot and stops.</strong> Use the map toolbar (below) to click a depot and stops, or press <strong>Draw</strong> to place that many random stops.{" "}
                  <strong>Clear</strong> removes them.
                </li>
                <li>
                  <strong>Vehicles.</strong> Leave it on <em>auto</em> and the app picks enough vans so they are about 85% full.
                </li>
                <li>
                  <strong>Capacity.</strong> How much load one van can carry. Each stop asks for a random amount (5 to 25). If one stop needs more than a whole van can
                  carry, the app warns you.
                </li>
                <li>
                  <strong>Time windows (demo).</strong> Tick it if stops must be served within a time slot. Each stop gets a random slot 30 to 60 minutes wide. A van
                  that arrives early waits; one that arrives late costs 10 per minute. <em>Service time</em> is the minutes spent at each stop. The results then show
                  every stop's arrival against its slot.
                </li>
              </ul>
              <Figure narrow src="time-windows" alt="The delivery problem section with time windows ticked" caption="Ticking “Time windows (demo)” adds the service time and explains the rule. Route search cannot handle time windows yet." />
            </section>

            <section id="guide-solver">
              <h3>03 · Solver</h3>
              <p>
                <strong>What to minimize.</strong> Choose what “best” means. <em>Fastest</em> (the default) means the fewest minutes of driving. <em>Shortest</em> means the
                fewest kilometres, but that can send vans into traffic, so the minutes and the time stuck in jams go up. <em>Avoid jams</em> counts the minutes lost to
                congestion as well. <em>Balanced</em> mixes all three. You can also drag the three sliders. The results always show the real minutes, kilometres and
                congestion delay, whatever you chose.
              </p>
              <Figure narrow src="weights" alt="The What to minimize presets and the three sliders" caption="The presets set the sliders for you. Only the proportions matter." />

              <p>
                <strong>Algorithm.</strong> The method that searches for good routes:
              </p>
              <ul>
                <li>
                  <strong>QPSO</strong> (the default) is this project's quantum-inspired method. A swarm of candidate plans moves step by step towards better ones.
                  “Quantum-inspired” means it borrows an idea from quantum physics; it runs on a normal computer.
                </li>
                <li>
                  <strong>Classical PSO</strong> and <strong>Genetic algorithm</strong> are well-known methods, there to compare against. <strong>Nearest neighbour</strong> is a
                  simple baseline: always drive to the closest stop not yet visited.
                </li>
                <li>
                  <strong>Route search</strong> is a different, swarm-free method. It keeps improving a plan by moving and swapping stops between vans until its time limit.
                  In our tests it found cheaper plans than QPSO on 15 to 100 stops, and on small problems (up to 14 stops) it found the exact best plan every time. It is an
                  option; QPSO stays the default.
                </li>
              </ul>
              <Figure narrow src="route-search" alt="The algorithm menu set to Route search, with its time limit" caption="Choosing Route search swaps the swarm settings for a time limit." />
              <ul>
                <li>
                  <strong>Particles</strong> is how many candidate plans the swarm keeps at once, and <strong>Iterations</strong> is how many rounds of improvement it runs.
                  More is slower and can be better. <strong>Seed</strong>: the same number gives the same result again.
                </li>
                <li>
                  <strong>Warm start</strong> begins the search from a sensible route instead of a random guess. It matters a lot on big problems (50 stops or more). On small
                  problems it makes no clear difference. Untick it to watch the algorithms compete from scratch.
                </li>
                <li>
                  <strong>Polish routes</strong> is a clean-up at the end: it reorders stops inside a route and moves stops between vans when that makes the plan cheaper. On
                  small problems it gives most of the quality.
                </li>
              </ul>
              <p>
                <strong>Optimize routes</strong> runs the solver. <strong>Benchmark</strong> runs several methods on the same problem so you can compare them.
              </p>
            </section>

            <section id="guide-results">
              <h3>Reading the results</h3>
              <p>The <em>Route plan</em> tab at the bottom explains the plan:</p>
              <ul>
                <li>
                  <strong>Total driving, all vans</strong> adds up every van's minutes. <strong>Job finishes in</strong> is the longest single van, because the vans drive at
                  the same time.
                </li>
                <li>
                  <strong>Congestion delay</strong> is how many of those minutes were lost to traffic, compared with empty roads.
                </li>
                <li>
                  <strong>Vehicles used</strong> and <strong>Capacity</strong> (“all respected”, or how much a van is overloaded).
                </li>
                <li>
                  <strong>Polish saved</strong> is how much the final clean-up improved the plan. The table lists each van's stops, load, minutes and kilometres, and the
                  chart shows how the best plan improved while the search ran.
                </li>
              </ul>
              <Figure src="results" alt="The Route plan tab with the result tiles and the table" caption="The Route plan tab after pressing Optimize routes." />
              <p>
                The <em>Algorithm benchmark</em> tab shows the methods side by side. Look at two columns: what each method found <em>by itself</em> (raw) and after the polish.
                An honest reading: from a cold start, QPSO is usually clearly better than classical PSO on its own. With the warm start on (the default), all the swarms begin
                from the same route, and once the polish is added the methods often end level, as in this example. Untick <em>Warm start</em> in section 03 to compare them from scratch.
              </p>
              <Figure src="benchmark" alt="The Algorithm benchmark tab" caption="Every method gets the same problem and the same budget. Here the warm start makes the three swarms end level; the nearest-neighbour baseline is clearly behind before the polish." />
            </section>

            <section id="guide-traffic">
              <h3>04 · Traffic</h3>
              <p>
                <strong>Free flow</strong> means empty roads, <strong>Random</strong> gives each road its own traffic, and <strong>Rush hour</strong> makes the centre of the
                map the busiest. The map repaints, and with <em>Re-optimize automatically</em> ticked the plan is recomputed, so you can watch routes detour around jams.
              </p>
              <p>
                On a <strong>Real city</strong> you can use real traffic. <strong>Fetch live traffic</strong> asks TomTom (about 25 seconds, and it needs a key set up by
                whoever runs the app). <strong>Save snapshot</strong> keeps that reading. Under <em>Recorded traffic</em>, pick a saved snapshot and press{" "}
                <strong>Replay</strong> to play it back later, with no internet needed.
              </p>
              <Figure narrow src="traffic" alt="The traffic section with live traffic and a recorded snapshot to replay" caption="Replay plays back a saved real reading." />
              <p>The badge at the top right of the map always says where the traffic comes from:</p>
              <div className="guide-badges">
                {BADGES.map(({ info, text }) => (
                  <div className="guide-badge-row" key={info.kind}>
                    <TrafficBadge info={info} inline />
                    <span>{text}</span>
                  </div>
                ))}
              </div>
            </section>

            <section id="guide-closures">
              <h3>Road closures (what-if)</h3>
              <ol className="guide-steps">
                <li>
                  Press <strong>block road</strong> on the map toolbar.
                </li>
                <li>Click a road. It turns red with a cross, and every plan and route now goes around it.</li>
                <li>
                  A banner at the bottom of the map says what the closure cost, against the same plan with every road open. Click the red road again to reopen it, or press{" "}
                  <strong>Reopen all</strong> in the sidebar.
                </li>
              </ol>
              <Figure src="closures" alt="A map with one closed road and the what-if banner" caption="One road closed: the plan takes longer, and the banner says by how much." />
              <p className="guide-note">
                If closures cut a place off completely, it is marked with a red circle and stops there cannot be served; the app says which ones. A closure cannot really
                save time. If the banner ever shows a saving, that is the random search finding a better plan the second time, not the closure. Press Optimize again, or use
                Route search, which is steadier. In our tests a closed road on a plan cost about 1% on average.
              </p>
            </section>

            <section id="guide-path">
              <h3>05 · Shortest path</h3>
              <p>
                The quickest way between two places. Press <strong>set A</strong> on the map toolbar and click a dot on the map, then <strong>set B</strong> and click another
                dot. Then press <strong>Find route</strong>, or <strong>Compare all four</strong>.
              </p>
              <ul>
                <li>
                  <strong>Dijkstra</strong> is an exact method: it always finds the best route, in a few thousandths of a second.
                </li>
                <li>
                  <strong>QPSO, classical PSO and the genetic algorithm</strong> search for the same route with particles. They usually come very close but can end a little
                  above the best. The <em>Above optimum</em> column says by how much; “optimal” means they found the best.
                </li>
              </ul>
              <Figure src="shortest-path-map" alt="A map with the exact route and the searched routes between A and B" caption="The wide dark line is the exact route. Each search method is drawn as a dotted line on top of it, so where a search found the best route its line hides on the dark one." />
              <Figure src="shortest-path-table" alt="The comparison table for the shortest path" caption="Cost, minutes and kilometres for each method, and how far above the best each one ended." />
              <p className="guide-note">For one route you would simply use Dijkstra. The other methods are here to show that the same machinery also works on a second kind of problem.</p>
            </section>

            <section id="guide-panels">
              <h3>Toolbar and panels</h3>
              <p>
                The <strong>map toolbar</strong> puts things on the map: press a button, then click the map. Press it again to turn it off. Click close to a dot or a road.
              </p>
              <ul>
                <li>
                  <strong>set depot</strong> and <strong>toggle stops</strong> choose where the vans start and where they deliver.
                </li>
                <li>
                  <strong>set A</strong> and <strong>set B</strong> choose the two ends of a shortest path.
                </li>
                <li>
                  <strong>block road</strong> closes or reopens a road.
                </li>
              </ul>
              <Figure narrow src="toolbar" alt="The map toolbar" caption="The map toolbar, at the top left of the map." />
              <ul>
                <li>
                  <strong>Sidebar:</strong> the button at its top left collapses it to a thin strip of icons (click an icon to jump to that section). Drag its right edge to
                  resize it; double-click the edge to reset.
                </li>
                <li>
                  <strong>Bottom panel:</strong> the two small buttons at the right of its tabs minimize or maximize it, and you can drag its top edge to resize it.
                </li>
              </ul>
            </section>

            <section id="guide-notes">
              <h3>Good to know</h3>
              <ul>
                <li>Stops and demands are random each time you press Draw, and the search is randomized too, so numbers change between runs. The same seed and the same stops give the same result.</li>
                <li>The app handles up to 150 stops. The time windows and demands are demo data, not real orders.</li>
                <li>From a cold start QPSO is a much stronger optimizer than classical PSO on its own, but with the warm start and the polish on, the methods end close together and often level. The benchmark tab shows both columns.</li>
                <li>
                  The full method and every measurement (with the cases where QPSO does not win) are written up in <code>docs/MATH_FORMULATION.md</code> and{" "}
                  <code>docs/BENCHMARKS.md</code>.
                </li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
