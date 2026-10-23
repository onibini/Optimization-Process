"""Run ``main.py`` once per site, one after another, with the same configuration.

The compute PC runs one job at a time well (WAMIT uses all NCPU cores), so several sites are queued inside one job::

    .\\scripts\\remote.ps1 submit -Config my_config.cfg -Name cmaes_sites -Script scripts/experiments/run_sites.py `
        -ScriptArgs "--sites 1 2 3"

For each site a copy of the configuration with ``SiteID`` replaced is written next to it (``config_site<N>.cfg``)
and passed to ``main.main``. A failing site is reported and the next one still runs; the exit status is 1 if any
site failed.
"""

import argparse
import os
import re
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import main as wec_main  # noqa: E402

SITE_LINE = re.compile(r"^(\s*)\S+(\s+SiteID\b.*)$", re.M)


def site_config(text, site_id):
    """Configuration text with the ``SiteID`` value replaced."""
    new, count = SITE_LINE.subn(lambda m: f"{m.group(1)}{site_id}{m.group(2)}", text, count=1)
    if count != 1:
        raise ValueError("SiteID line not found in the configuration")
    return new


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sites", nargs="+", type=int, required=True, help="SiteID values (data/env_data.csv)")
    parser.add_argument("--config", default="config.cfg")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        text = f.read()
    failed = []
    for site_id in args.sites:
        path = os.path.join(os.path.dirname(os.path.abspath(args.config)), f"config_site{site_id}.cfg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(site_config(text, site_id))
        print(f"\n######## SiteID {site_id} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ########", flush=True)
        start = time.time()
        try:
            wec_main.main(path)
        except (Exception, SystemExit):
            traceback.print_exc()
            failed.append(site_id)
        print(f"######## SiteID {site_id} finished in {(time.time() - start) / 3600:.2f} h ########", flush=True)
    if failed:
        print(f"failed sites: {failed}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
