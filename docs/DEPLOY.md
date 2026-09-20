# Deploying the prototype for free

The app is one Docker image (`docker compose up --build` runs it locally; see the README). This page says where that image can
run **on the public internet at no cost**, what each option gives up, and the exact steps. Free tiers change often: the facts below
were checked in September 2026, so read the provider's current terms before you rely on one.

## What a public deployment is (and is not)

- **Works:** the whole app: delivery plans with QPSO, PSO, GA and the route search, the benchmark, simulated traffic (random, rush
  hour), road closures, cost weights, time windows, the shortest path, the Guide, and the four preset real cities (Connaught Place,
  Sector 18 Noida, MG Road, CST/Fort Mumbai), which now ship inside the image and load in about a second.
- **Real traffic is optional.** Live traffic needs a TomTom key, and a public site lets anyone spend its 2,500 requests a day; the
  recorded MG Road snapshot is TomTom data. Both are now supported on a public site (the snapshot ships in
  `backend/data/recorded_traffic/`, the key is set as a private environment variable on the host); see "Things to decide or watch"
  below before you turn them on.
- **Memory and speed:** the container uses about 66 MiB when idle and 154 to 172 MiB at its peak during the full demo rehearsal. Plans
  take about a second on a normal CPU; the route search runs up to its time limit (10 s by default).
- **State is in memory.** Loaded maps live in the one running process. If the host restarts or scales it to zero, a page that was open
  says the map is unknown; reloading the page makes a new one. Open the site a minute before a demo to wake it.

## The route we chose: Render (permanent, needs no laptop)

Render runs the Docker image from the GitHub repository on its free tier: no card, no laptop, and an address you name yourself,
**https://quantum-inspired-route-optimizer.onrender.com** (Render adds a suffix if the name is already taken; use whatever address it
shows). The repository already contains everything Render needs: `render.yaml` (the service definition), the `Dockerfile`, the four
preset city maps and the recorded MG Road traffic. You do these steps yourself, because they involve your accounts:

1. **Push `main` to GitHub** so Render can see the latest files (`git push origin main`).
2. **Sign up at render.com with your GitHub account** (no card is asked for the free plan).
3. **New, then Blueprint**, choose the `SIH2026` repository and press **Apply**. Render reads `render.yaml` and builds the image
   (about 5 to 8 minutes the first time). If it says the Blueprint is invalid, use **New, then Web Service** instead: pick the
   repository, Runtime *Docker*, Instance type *Free*, Region *Singapore*, Health check path `/health`, and the same service name.
4. **Add the TomTom key** in the service's **Environment** tab: name `TOMTOM_API_KEY`, your key as the value, then save (Render
   redeploys). It stays in Render's private settings and never enters the repository. Without it the recorded traffic still works, and
   only "Fetch live traffic" is unavailable.
5. **Open the address** and check it: `cd backend && python scripts/demo_rehearsal.py --base https://quantum-inspired-route-optimizer.onrender.com`
   (add `--public` if you skipped the key).
6. **Keep it awake.** Render puts a free service to sleep after 15 minutes without a visit and needs about a minute to wake it. The
   repository has a GitHub Actions job (`.github/workflows/keepalive.yml`) that visits the site every 10 minutes. It starts by
   itself once `main` is on GitHub; check the **Actions** tab. If your Render address differs from the one above, set the repository
   variable `SITE_URL` (Settings, Secrets and variables, Actions, Variables). Scheduled jobs run about every 10 minutes but can be
   late, and GitHub pauses them after 60 days without any repository activity. As a second safety net you can add a free monitor such as
   UptimeRobot on `/health`. Keeping one service awake for a month uses 744 of Render's 750 free hours, so keep it the only free service.

**Changing the radius.** The four preset cities load at once at any radius up to 2000 m, on any host and with no internet: they ship at 1200 m
and 2000 m, and a smaller radius is cut out of the 2000 m map (measured against a real download: within 0.4% of its intersections and
0.6% of its roads). Any other place, or a radius above 2000 m, is downloaded from OpenStreetMap, which needs the server to reach one of four
public Overpass servers. If a host blocks them (a free Render instance could not reach the main one), the error now names each server instead
of showing a cryptic message, and only those downloads fail. On the free 0.1 CPU a download that does work takes about 2 minutes.

**What judges get.** Everything in the app, including the four cities, the recorded MG Road traffic (labelled RECORDED) and, if you
added the key, live TomTom traffic. The map cache and any state are lost when Render restarts the service; the bundled maps are copied
back in on start and a warm-up loads them, so a city still opens in a fraction of a second.

**Speed.** The free instance is about a tenth of a CPU. Measured with the same limits on your laptop (0.1 CPU, 512 MB): the default
plan takes about 7 seconds instead of 0.3, the full benchmark about 40 seconds instead of 2, and the whole demo rehearsal 155 seconds
instead of 6. Everything works and the interface shows its progress messages, but it is slow, so the demo video (recorded locally) is
the version to show at full speed. Memory is fine (peak 153 MiB of 512).

**Things to decide or watch.**
- *Public data:* the recorded snapshot in `backend/data/recorded_traffic/` is TomTom data, and if the repository is public it is
  published there (the file carries a README with the credit). Check TomTom's terms; remove the file and push again if in doubt.
- *Quota:* with a key set, anyone with the link can press "Fetch live traffic"; each visitor's first fetch costs about 80 of the free
  2,500 requests a day. When the quota is used up, that button shows an error and the recorded traffic keeps working. Remove the key
  in Render's Environment tab to switch live traffic off.
- *Updates:* every push to `main` redeploys the site automatically (`autoDeployTrigger: commit`); stop that in Render's settings if
  you want to freeze the version judges see.
- *Taking it down:* delete the service in the Render dashboard.

## Options, in order of recommendation

| Option | Cost | Card needed | Always on | Verdict |
|---|---|---|---|---|
| **A. Google Cloud Run** | free monthly allowance (2 million requests, 180,000 vCPU-seconds, 360,000 GiB-seconds) | yes, for identity check | scales to zero, wakes in seconds | **Best for a link that stays up** |
| **B. Your machine + a Cloudflare quick tunnel** | free | no, and no account | only while your laptop runs | **Best for a live demo or judging session**, and it keeps real traffic |
| **C. Render free web service** (the route we chose, see above) | free | no | sleeps after 15 min unless kept awake, about a minute to wake | Fits in memory, but only 0.1 CPU, so plans are slow |

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
