"""
Fetch the CVRPLIB "X" instances (Uchoa et al., 2017) with 100-200 customers, plus their best-known solutions, into
backend/data/cvrplib/ (git-ignored: third-party data). About 22 x 3 KB; used by scripts/cvrplib_benchmark.py and
docs/BENCHMARKS.md, Finding 14.

    python scripts/fetch_cvrplib.py            # download what is missing
    python scripts/fetch_cvrplib.py --force    # download everything again

Source: https://galgos.inf.puc-rio.br/cvrplib/ (the repository of Uchoa, Pecin, Pessoa, Poggi, Subramanian and
Vidal, hosted by PUC-Rio). Files are served by numeric id; the ids and the optimal costs below were read from its
instance listing (every instance in this list is marked proven optimal there). Nothing is saved unless it parses as
the expected instance and its solution file's cost matches both the listing and a recomputation from the coordinates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.cvrplib import check_solution, parse_instance, parse_solution, solution_cost  # noqa: E402
from app.data.http import open_url  # noqa: E402

BASE = "https://galgos.inf.puc-rio.br/cvrplib/index.php/en/download"
DATA = Path(__file__).resolve().parent.parent / "data" / "cvrplib"
MAX_BYTES = 1_000_000

# name: (CVRPLIB id, proven optimal cost)
CATALOGUE = {
    "X-n101-k25": (158, 27591),
    "X-n106-k14": (159, 26362),
    "X-n110-k13": (160, 14971),
    "X-n115-k10": (161, 12747),
    "X-n120-k6": (162, 13332),
    "X-n125-k30": (163, 55539),
    "X-n129-k18": (164, 28940),
    "X-n134-k13": (165, 10916),
    "X-n139-k10": (166, 13590),
    "X-n143-k7": (167, 15700),
    "X-n148-k46": (168, 43448),
    "X-n153-k22": (169, 21220),
    "X-n157-k13": (170, 16876),
    "X-n162-k11": (171, 14138),
    "X-n167-k10": (172, 20557),
    "X-n172-k51": (173, 45607),
    "X-n176-k26": (174, 47812),
    "X-n181-k23": (175, 25569),
    "X-n186-k15": (176, 24145),
    "X-n190-k8": (177, 16980),
    "X-n195-k51": (178, 44225),
    "X-n200-k36": (179, 58578),
}


def download(kind: str, ident: int) -> str:
    with open_url(f"{BASE}/{kind}/{ident}", timeout=60) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"{kind}/{ident} is larger than {MAX_BYTES} bytes; refusing it")
    return body.decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="download again even if the files exist")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)

    failed = []
    for name, (ident, optimal) in CATALOGUE.items():
        vrp_path, sol_path = DATA / f"{name}.vrp", DATA / f"{name}.sol"
        if vrp_path.exists() and sol_path.exists() and not args.force:
            print(f"{name}: already there ({vrp_path.stat().st_size} + {sol_path.stat().st_size} bytes)")
            continue
        try:
            vrp_text, sol_text = download("instance", ident), download("bks", ident)
            instance = parse_instance(vrp_text)
            routes, stated = parse_solution(sol_text)
            assert instance.name == name, f"the file is {instance.name}, expected {name}"
            check_solution(instance, routes)
            assert stated == optimal, f"the solution file says {stated}, the listing says {optimal}"
            assert solution_cost(instance, routes) == stated, "the stated cost is not what the routes cost"
        except Exception as error:  # noqa: BLE001 - report every instance, then fail once
            print(f"{name}: NOT SAVED ({type(error).__name__}: {error})")
            failed.append(name)
            continue
        vrp_path.write_text(vrp_text, encoding="utf-8", newline="")
        sol_path.write_text(sol_text, encoding="utf-8", newline="")
        print(f"{name}: saved {len(vrp_text.encode())} + {len(sol_text.encode())} bytes (optimal {optimal:,}, {instance.n_customers} customers, capacity {instance.capacity})")

    total = sum(p.stat().st_size for p in DATA.glob("*") if p.is_file())
    print(f"\n{len(CATALOGUE) - len(failed)} of {len(CATALOGUE)} instances in {DATA} ({total / 1024:.0f} KB in all)")
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
