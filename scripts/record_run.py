"""Record a dbt run's results in the warehouse, for pipeline-health monitoring.

Reads dbt/target/run_results.json after `dbt build` and appends one row per node to
`ops.dbt_node_runs`, plus one row per run to `ops.dbt_runs` (status counts, total time, and how
fresh the newest loaded payment is). The Streamlit app's Pipeline health tab reads these tables.

Usage
    python scripts/record_run.py --db warehouse/receivables.duckdb
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/receivables.duckdb")
    ap.add_argument("--results", default=str(ROOT / "dbt" / "target" / "run_results.json"))
    args = ap.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    run_id = results["metadata"]["invocation_id"]
    generated_at = pd.Timestamp(results["metadata"]["generated_at"]).tz_localize(None)
    nodes = pd.DataFrame([{
        "run_id": run_id,
        "generated_at": generated_at,
        "unique_id": r["unique_id"],
        "resource_type": r["unique_id"].split(".")[0],
        "name": r["unique_id"].split(".")[-1],
        "status": r["status"],
        "execution_time_s": round(r["execution_time"], 3),
        "failures": r.get("failures") or 0,
    } for r in results["results"]])

    with duckdb.connect(args.db) as con:
        con.execute("create schema if not exists ops")
        con.execute("""create table if not exists ops.dbt_node_runs (
            run_id varchar, generated_at timestamp, unique_id varchar, resource_type varchar, name varchar,
            status varchar, execution_time_s double, failures bigint)""")
        con.execute("delete from ops.dbt_node_runs where run_id = ?", [run_id])
        con.register("nodes", nodes)
        con.execute("insert into ops.dbt_node_runs select * from nodes")
        freshest = con.execute("select max(loaded_at) from bronze.payments").fetchone()[0]
        run = pd.DataFrame([{
            "run_id": run_id,
            "generated_at": generated_at,
            "nodes": len(nodes),
            "passed": int(nodes["status"].isin(["pass", "success"]).sum()),
            "failed": int(nodes["status"].isin(["fail", "error"]).sum()),
            "elapsed_s": round(results.get("elapsed_time", 0.0), 2),
            "newest_payment_loaded_at": freshest,
        }])
        con.execute("""create table if not exists ops.dbt_runs (
            run_id varchar, generated_at timestamp, nodes bigint, passed bigint, failed bigint,
            elapsed_s double, newest_payment_loaded_at timestamp)""")
        con.execute("delete from ops.dbt_runs where run_id = ?", [run_id])
        con.register("run", run)
        con.execute("insert into ops.dbt_runs select * from run")
    r = run.iloc[0]
    print(f"recorded run {run_id[:8]}: {r.passed}/{r.nodes} passed, {r.failed} failed, {r.elapsed_s}s")


if __name__ == "__main__":
    main()
