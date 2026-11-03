"""Collect the trial histories of finished runs into the evaluation database (``data/eval_db``).

Every ``*_trial_history.csv`` with its ``*_config.json`` under the given folders is grouped by the settings
fingerprint (``src/utils/eval_db.py``) and merged into one CSV per fingerprint. Designs already in the database are
kept; a stored value that differs from a new one by more than ``--tolerance`` is reported as a conflict and the
stored value is kept. Runs whose settings cannot be fingerprinted (older logs without these keys) are skipped.

    python scripts/build_eval_db.py                     # results/ and logs/
    python scripts/build_eval_db.py results/20261104_050221_de_nosort_sites21

``scripts/remote.ps1 fetch`` runs this after every fetch. Set ``EvalCache 1`` in config.cfg to use the database.
"""

import argparse
import collections
import csv
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.utils.eval_db import (  # noqa: E402
    DEFAULT_DB_DIR,
    db_name,
    fingerprint,
    merge_records,
    read_records,
    write_records,
)


def trial_rows(path):
    """``(vector, fitness, powers, penalized)`` rows of one trial history."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        v_cols = [c for c in reader.fieldnames if c.startswith("v")]
        p_cols = [c for c in reader.fieldnames if c.startswith("p") and c[1:].isdigit()]
        for row in reader:
            fitness = float(row["fitness"])
            penalized = bool(int(row["penalized"])) if row.get("penalized") not in (None, "") else fitness < 0
            rows.append(([float(row[c]) for c in v_cols], fitness, [float(row[c]) for c in p_cols], penalized))
    return rows


def find_runs(folders):
    for folder in folders:
        pattern = os.path.join(folder, "**", "*_trial_history.csv")
        for path in sorted(glob.glob(pattern, recursive=True)):
            config_path = path[: -len("_trial_history.csv")] + "_config.json"
            if os.path.exists(config_path):
                yield path, config_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folders", nargs="*", default=[os.path.join(ROOT, "results"), os.path.join(ROOT, "logs")])
    parser.add_argument("--db-dir", default=DEFAULT_DB_DIR)
    parser.add_argument("--tolerance", type=float, default=1e-4, help="relative difference treated as a conflict")
    args = parser.parse_args(argv)

    groups = collections.defaultdict(list)
    skipped = 0
    for trial_path, config_path in find_runs(args.folders):
        with open(config_path, encoding="utf-8") as f:
            fp = fingerprint(json.load(f))
        if fp is None:
            skipped += 1
            continue
        groups[db_name(fp)].append((fp, trial_path))

    for name, runs in sorted(groups.items()):
        path = os.path.join(args.db_dir, name + ".csv")
        records = read_records(path)
        before = len(records)
        added = conflicts = 0
        for _, trial_path in runs:
            source = os.path.basename(trial_path)[: -len("_trial_history.csv")]
            a, c = merge_records(records, trial_rows(trial_path), source, args.tolerance)
            added, conflicts = added + a, conflicts + c
        if added or not os.path.exists(path):
            write_records(path, runs[0][0], records)
        physics = sum(1 for r in records.values() if not r[3])
        print(
            f"{name}: {len(records)} designs ({physics} WAMIT), {added} new from {len(runs)} runs"
            f"{f', {conflicts} conflicting values kept as stored' if conflicts else ''} (was {before})"
        )
    if skipped:
        print(f"skipped {skipped} runs whose settings are not recorded (older logs)")


if __name__ == "__main__":
    main()
