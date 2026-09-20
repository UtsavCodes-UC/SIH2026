# Recorded traffic that ships with the app

`osm_12.9758_77.6068_1200_drive__20260919T125306Z.json` is one recording of real traffic on the MG Road, Bengaluru preset map
(radius 1200 m), taken from TomTom's Traffic Flow API on 2026-09-19 at 12:53 UTC (6:23 pm in Bengaluru). It holds a congestion
factor for each road (541 of 1,223 roads were measured directly; the rest are estimated from their neighbours), so the app can
replay real traffic without a live fetch and without a TomTom key.

The app labels a replay RECORDED, never LIVE, and shows "Traffic data © TomTom" beside it. Traffic data © TomTom. Map data ©
OpenStreetMap contributors. It is included with the owner's decision to publish it; check TomTom's terms before redistributing it
further. Recordings you make yourself are saved to `backend/data/traffic_snapshots/` (not tracked by git) and are listed first.
