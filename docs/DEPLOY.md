# Deploying the prototype for free

The app is one Docker image (`docker compose up --build` runs it locally; see the README). This page says where that image can
run **on the public internet at no cost**, what each option gives up, and the exact steps. Free tiers change often: the facts below
were checked in September 2026, so read the provider's current terms before you rely on one.

## What a public deployment is (and is not)

- **Works:** the whole app: delivery plans with QPSO, PSO, GA and the route search, the benchmark, simulated traffic (random, rush
  hour), road closures, cost weights, time windows, the shortest path, the Guide, and the four preset real cities (Connaught Place,
  Sector 18 Noida, MG Road, CST/Fort Mumbai), which now ship inside the image and load in about a second.
- **Not there by default:** real traffic. Live traffic needs a TomTom key, and a public site would let anyone spend its 2,500
  requests a day, so do not set one. The recorded snapshot is TomTom data and is not shipped either (check TomTom's terms before
  redistributing it). Show recorded and live traffic from your own machine or in the demo video.
- **Memory and speed:** the container uses about 66 MiB when idle and 154 to 172 MiB at its peak during the full demo rehearsal. Plans
  take about a second on a normal CPU; the route search runs up to its time limit (10 s by default).
- **State is in memory.** Loaded maps live in the one running process. If the host restarts or scales it to zero, a page that was open
  says the map is unknown; reloading the page makes a new one. Open the site a minute before a demo to wake it.

## Options, in order of recommendation

| Option | Cost | Card needed | Always on | Verdict |
|---|---|---|---|---|
| **A. Google Cloud Run** | free monthly allowance (2 million requests, 180,000 vCPU-seconds, 360,000 GiB-seconds) | yes, for identity check | scales to zero, wakes in seconds | **Best for a link that stays up** |
| **B. Your machine + a Cloudflare quick tunnel** | free | no, and no account | only while your laptop runs | **Best for a live demo or judging session**, and it keeps real traffic |
| C. Render free web service | free | not stated in the sources I found | sleeps after 15 min, 30 to 60 s to wake | Fits in memory, but only 0.1 CPU, so plans are slow |

Checked and **not** free or not open to new users: Hugging Face Docker Spaces (creating one now needs a paid plan), Fly.io (no free
tier after the 2024 change), Koyeb (its free tier is reported closed to new users since the Mistral AI acquisition), Oracle Cloud
Always Free (still there but cut to 2 OCPU / 12 GB ARM in June 2026, and the image would need an ARM build), Railway (a trial credit,
not a free plan).

### A. Google Cloud Run

You do these steps yourself: they involve your Google account and a card, which I cannot and should not handle.

1. Create a Google Cloud project and attach a billing account (Console, Billing). Google asks for a card to verify you; it does not
   charge inside the free allowance. In Billing, set a **budget alert** (for example 1 USD) so a surprise cannot go unnoticed.
2. Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install), then from the repository root:

   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
   gcloud run deploy sih26137 --source . --region us-central1 --allow-unauthenticated \
     --memory 1Gi --cpu 1 --cpu-boost --max-instances 1 --concurrency 8 --timeout 300
   ```

   Google builds the image from the `Dockerfile` in the cloud (about 5 minutes the first time) and prints a `https://...run.app` address.
   The image reads the `PORT` that Cloud Run provides, so no port setting is needed.
3. Check it, from your machine:

   ```bash
   cd backend && python scripts/demo_rehearsal.py --public --base https://YOUR-SERVICE.run.app
   ```

   It should say `0 check(s) failed`; it notes that real traffic is absent on purpose.
4. When judging is over, remove it: `gcloud run services delete sih26137 --region us-central1`.

Why these settings: `--max-instances 1` because maps are kept in one process's memory and it caps any cost; `--concurrency 8` because
a plan uses a CPU for a second; `--memory 1Gi` is several times the measured peak; `us-central1` is a Tier 1 region, where the free
allowance applies in full. Cost risk: inside the allowance it is free (180,000 vCPU-seconds is about 50 hours of continuous CPU a
month); an abusive crawler could use it up, which is what the budget alert and `--max-instances 1` are for. Building the image also
uses Cloud Build and Artifact Registry, which have small free allowances of their own.

### B. Your machine and a Cloudflare quick tunnel

No account, no card, and it keeps the recorded and live traffic scenes. The address only exists while it runs.

1. Start the app: `docker compose up -d` (then it is on http://localhost:8000).
2. Install `cloudflared` (a download from Cloudflare; on Windows `winget install Cloudflare.cloudflared`), then run:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

   It prints an address like `https://random-words.trycloudflare.com`. Anyone with it can use your app while the command runs.
3. **Take the key out first** (empty `TOMTOM_API_KEY` in `backend/.env`, then restart the container) unless you are showing live traffic:
   anyone with the link could otherwise press "Fetch live traffic" and spend your quota. The 5-minute reuse of a recent reading limits
   this but does not remove it.
4. Quick tunnels are rate-limited, have no uptime guarantee and the address changes each time, so give the address out only for the
   session and keep the laptop awake and online.

### C. Render free web service

Create a Web Service from your GitHub repository, choose Docker and the free instance type. Render passes `PORT` and the image reads
it. It fits in memory (512 MB against a 172 MiB peak), but the instance has 0.1 CPU, so plans and the route search run roughly ten
times slower than on a laptop, and it sleeps after 15 minutes idle. Use it only as a fallback.

## Hardening before you share a link widely (optional, not done)

The API has no login. Anyone can call it, including "load any place" (a download from OpenStreetMap) and the largest benchmark. For a
hackathon that is normally fine; if it worries you, the smallest useful change is a switch that limits the map endpoint to the four
bundled places. Ask if you want it.

## Sources

- [Hugging Face: Spaces overview](https://huggingface.co/docs/hub/spaces-overview) (Docker Spaces need a paid plan to create; free CPU is 2 vCPU, 16 GB, not persistent, sleeps when unused)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing) and the [free trial FAQs](https://cloud.google.com/signup-faqs) (free allowance; card for verification)
- Render's free web service limits and spin-down, as reported in [FreeTier.co](https://freetier.co/directory/products/render) and similar 2026 reviews
- [Oracle: Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) and [InfoQ on the June 2026 cut](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- Cloudflare quick tunnels: [cloudflared documentation](https://deepwiki.com/cloudflare/cloudflared/3.4-quick-tunnels)
