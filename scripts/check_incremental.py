"""Prove the incremental cash-application fact equals a full rebuild, including late-loading payments.

1. Full refresh with only what had loaded by --cutoff (the "first load").
2. Incremental run with everything loaded since (the "next load").
3. Snapshot the result, full-refresh the fact, and compare both ways with EXCEPT.

Usage
    python scripts/check_incremental.py --db warehouse/receivables.duckdb --cutoff "2025-03-15 00:00:00"
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
FACT = "gold.fct_payment_application"


def dbt(db: str, *args: str) -> None:
    exe = Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")
    cmd = [str(exe) if exe.exists() else "dbt", *args, "--profiles-dir", "."]
    env = {**os.environ, "DUCKDB_PATH": str(Path(db).resolve())}
    print("$", " ".join(cmd[1:]))
    subprocess.run(cmd, cwd=ROOT / "dbt", env=env, check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/receivables.duckdb")
    ap.add_argument("--cutoff", default="2025-03-15 00:00:00")
    args = ap.parse_args()

    select = ["-s", "+fct_payment_application", "--exclude", "test_type:unit"]
    dbt(args.db, "run", *select, "--full-refresh", "--vars", f'{{load_cutoff: "{args.cutoff}"}}')
    with duckdb.connect(args.db) as con:
        first = con.sql(f"select count(*) from {FACT}").fetchone()[0]
        late = con.sql(f"""select count(*) from bronze.payment_applications
                           where applied_at < '{args.cutoff}' and loaded_at > '{args.cutoff}'""").fetchone()[0]

    dbt(args.db, "run", *select)
    with duckdb.connect(args.db) as con:
        con.execute("create schema if not exists audit")
        con.execute(f"create or replace table audit.fct_after_incremental as select * from {FACT}")

    dbt(args.db, "run", *select, "--full-refresh")
    with duckdb.connect(args.db) as con:
        full = con.sql(f"select count(*) from {FACT}").fetchone()[0]
        only_inc = con.sql(f"select count(*) from (select * from audit.fct_after_incremental except select * from {FACT})").fetchone()[0]
        only_full = con.sql(f"select count(*) from (select * from {FACT} except select * from audit.fct_after_incremental)").fetchone()[0]
        con.execute("drop schema audit cascade")

    print(f"first load rows: {first:,} | applications dated before the cutoff but loaded after: {late:,}")
    print(f"rows after incremental vs full refresh: {full:,} | only in incremental: {only_inc} | only in full: {only_full}")
    if only_inc or only_full:
        sys.exit("FAIL: incremental result differs from full refresh")
    print("PASS: incremental result equals full refresh")


if __name__ == "__main__":
    main()
