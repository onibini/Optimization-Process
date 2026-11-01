"""Run ``main.py`` once per site, one after another, with the same configuration.

The compute PC runs one job at a time well (WAMIT uses all NCPU cores), so several sites are queued inside one job::

    .\\scripts\\remote.ps1 submit -Config my_config.cfg -Name cmaes_sites -Script scripts/experiments/run_sites.py `
        -ScriptArgs "--sites 1 2 3"

For each site a copy of the configuration with ``SiteID`` replaced is written next to it (``config_site<N>.cfg``)
and passed to ``main.main``. A failing site is reported and the next one still runs; the exit status is 1 if any
site failed.

``--variants`` repeats all sites for several settings, one variant after another; each variant is a comma-separated
list of ``Key=Value`` replacements (``config_v<k>_site<N>.cfg``)::

    -ScriptArgs "--sites 2 3 --variants InitPop=1 InitPop=0"
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


def set_value(text, key, value):
    """Configuration text with the value of the (uncommented) ``key`` line replaced."""
    line = re.compile(rf"^(\s*)[^\s#]\S*(\s+{re.escape(key)}\b.*)$", re.M)
    new, count = line.subn(lambda m: f"{m.group(1)}{value}{m.group(2)}", text, count=1)
    if count != 1:
        raise ValueError(f"{key} line not found in the configuration")
    return new


def site_config(text, site_id):
    """Configuration text with the ``SiteID`` value replaced."""
    return set_value(text, "SiteID", site_id)


def parse_variant(spec):
    """``"InitPop=1,DEUpdate=2"`` -> ``[("InitPop", "1"), ("DEUpdate", "2")]``."""
    pairs = []
    for item in filter(None, spec.split(",")):
        key, sep, value = item.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ValueError(f"variant item must be Key=Value, got {item!r}")
        pairs.append((key.strip(), value.strip()))
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sites", nargs="+", type=int, required=True, help="SiteID values (data/env_data.csv)")
    parser.add_argument("--config", default="config.cfg")
    parser.add_argument("--variants", nargs="+", default=None, help="settings run one after another, e.g. InitPop=1")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        text = f.read()
    variants = [parse_variant(spec) for spec in args.variants] if args.variants else [[]]
    folder = os.path.dirname(os.path.abspath(args.config))
    failed = []
    for k, variant in enumerate(variants):
        base = text
        for key, value in variant:
            base = set_value(base, key, value)
        label = ", ".join(f"{key}={value}" for key, value in variant)
        if label:
            print(f"\n======== Variant {k + 1}/{len(variants)}: {label} ========", flush=True)
        for site_id in args.sites:
            name = f"config_v{k + 1}_site{site_id}.cfg" if args.variants else f"config_site{site_id}.cfg"
            path = os.path.join(folder, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(site_config(base, site_id))
            print(f"\n######## SiteID {site_id} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ########", flush=True)
            start = time.time()
            try:
                wec_main.main(path)
            except (Exception, SystemExit):
                traceback.print_exc()
                failed.append(f"{site_id} ({label})" if label else site_id)
            print(f"######## SiteID {site_id} finished in {(time.time() - start) / 3600:.2f} h ########", flush=True)
    if failed:
        print(f"failed sites: {failed}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
