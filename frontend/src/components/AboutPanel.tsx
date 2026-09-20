interface Props {
    onClose: () => void;
}

export default function AboutPanel({ onClose }: Props) {
    return (
        <div className="about-backdrop" onClick={onClose}>
            <div className="about-panel" role="dialog" aria-label="About" onClick={(e) => e.stopPropagation()}>
                <div className="about-header">
                    <h2>About</h2>
                    <button className="about-close" onClick={onClose} aria-label="Close">
                        ×
                    </button>
                </div>

                <div className="about-body">
                    <section>
                        <h3>Road Network</h3>
                        <p><strong>Synthetic tab</strong> – generate a fake city map.</p>
                        <ul>
                            <li><strong>Intersections</strong> – number of road junctions in the map. Set this to control how big/detailed the network is.</li>
                            <li><strong>Area (km)</strong> – size of the area the map covers. Set based on how large a region you want to simulate.</li>
                            <li><strong>Seed</strong> – a fixed number so the same map can be regenerated later. Keep it the same to reproduce a map, or change it to get a different random map.</li>
                            <li><strong>Generate network</strong> – creates the map based on the above. Click this after setting the values above.</li>
                        </ul>

                        <p><strong>Real city tab</strong> – use an actual city's roads instead.</p>
                        <ul>
                            <li><strong>Place</strong> – pick the real location (e.g. Connaught Place, New Delhi). Type or select the place you want to base the map on.</li>
                            <li><strong>Radius (m)</strong> – how far out from that place to pull roads, in meters. Increase for a wider area, decrease for a smaller, faster-loading one.</li>
                            <li><strong>Load road network</strong> – fetches the roads for that area. Click this to load it — first time takes a couple of minutes (downloading from OpenStreetMap); after that it's instant.</li>
                        </ul>

                        <p>Either way, once generated/loaded, you'll see a summary — number of intersections, roads, and average congestion. No action needed here, just confirms the network is ready.</p>
                    </section>

                    <section>
                        <h3>Delivery Problem</h3>
                        <ul>
                            <li><strong>Depot</strong> – the start/end point for all vehicles. Click on the map to set it, or use Random stops below.</li>
                            <li><strong>Stops</strong> – the delivery locations to visit. Click on the map to add them individually.</li>
                            <li><strong>Random stops + Draw/Clear</strong> – type a number and click Draw to auto-place that many stops randomly. Use this instead of clicking manually if you just want a quick test set. Click Clear to remove them and start over.</li>
                            <li><strong>Vehicles</strong> – number of delivery vehicles. Enter a number, or leave "auto" and let the tool decide for you.</li>
                            <li><strong>Capacity</strong> – how much load each vehicle can carry. Set this based on your scenario.</li>
                            <li>Demands at each stop are random (5–25) by default. No action needed — this is generated automatically.</li>
                        </ul>
                    </section>

                    <section>
                        <h3>Solver</h3>
                        <ul>
                            <li><strong>Algorithm</strong> – the method used to find routes (default QPSO). Leave as default, or change it if you want to compare methods.</li>
                            <li><strong>Particles</strong> – number of parallel "guesses" the algorithm explores at once. Increase for a wider search (slower), decrease for a faster but less thorough one.</li>
                            <li><strong>Iterations</strong> – number of improvement rounds it runs. Increase for potentially better routes (takes longer), decrease for a quicker result.</li>
                            <li><strong>Seed</strong> – fixed number for reproducible results. Keep the same to reproduce a run, or change for a different outcome.</li>
                            <li><strong>Warm start from a good route</strong> – starts the search from a decent route instead of from scratch. Keep this checked for faster/better results; uncheck it if you want to see how the algorithm performs from a cold start (useful with few stops).</li>
                            <li><strong>Polish routes</strong> – does a final cleanup pass after solving. Keep checked for tighter, more efficient final routes.</li>
                            <li><strong>Optimize routes</strong> – runs the solver and gives you the final routes. Click this once your network and delivery problem are set up.</li>
                            <li><strong>Benchmark</strong> – compares QPSO against other algorithms (PSO, GA, nearest neighbour). Click this if you want to see how QPSO stacks up against other methods on your setup.</li>
                        </ul>
                    </section>

                    <section>
                        <h3>Traffic</h3>
                        <ul>
                            <li><strong>Free flow</strong> – no traffic, all roads at full speed. Click to simulate ideal conditions.</li>
                            <li><strong>Random</strong> – randomly simulated congestion. Click to test route robustness under unpredictable traffic.</li>
                            <li><strong>Rush hour</strong> – simulated peak-time congestion. Click to test under heavy, realistic traffic.</li>
                            <li><strong>Fetch live traffic</strong> – pulls real traffic data (TomTom). Click this only when using a Real city network, to get actual current conditions.</li>
                            <li><strong>Save snapshot</strong> – saves the fetched traffic data for reuse. Click after fetching live traffic if you want to reuse that exact data later.</li>
                            <li><strong>Re-optimize automatically after traffic changes</strong> – recalculates routes automatically whenever traffic updates. Keep this checked if you want routes to stay up to date without manually re-running the solver each time.</li>
                        </ul>
                    </section>
                </div>
            </div>
        </div>
    );
}