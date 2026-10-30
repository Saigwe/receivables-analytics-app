"""Generate a synthetic accounts-receivable sub-ledger and GL control balances into DuckDB `bronze`.

There is no public dataset with real AR detail, so this generator is the real-data path, built from a
fixed seed. It is modelled on the shape of marketplace receivables, but every row is invented.

What it simulates
- Customers with a hidden payer profile (prompt, late, chronic, non-payer) that drives days to pay
- Invoices by segment and month; credit notes (4%) and disputes (3%); partial payments (10%)
- Bad-debt write-offs: unpaid invoices are written off 180 days past due (credit note, reason bad_debt_write_off)
- Cash application lag: some payments are applied days after they arrive (unapplied cash at month end)
- Customer changes over time (terms, segment, credit limit) for a type-2 customer dimension
- Late-loading payments (0.5% load 3-10 days after receipt) to test the incremental model
- Month-end GL AR control balance per currency, posted from the same events
- Customer contact phone numbers as typed into a CRM, with an answer key of the correct E.164 number

Usage
    python ingestion/generate_ar.py --db warehouse/receivables.duckdb                  # 25k customers, Jan 2024 - Jun 2025
    python ingestion/generate_ar.py --db warehouse/fixture.duckdb --customers 300 --start 2025-01-01
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

COUNTRIES = {"US": "USD", "CA": "CAD", "AU": "AUD"}
SEGMENTS = {  # weight, invoices per month, mean log amount, terms options
    "smb": (0.70, 1.0, 6.2, [15, 30]),
    "mid_market": (0.22, 2.0, 7.4, [30, 45]),
    "enterprise": (0.08, 4.0, 8.6, [45, 60]),
}
PROFILES = {  # weight, days after due date (mean, sd), share never paid
    "prompt": (0.55, (-3, 4), 0.0),
    "late": (0.30, (15, 10), 0.0),
    "chronic": (0.12, (45, 20), 0.02),
    "non_payer": (0.03, (75, 30), 0.55),
}
FX_START = {"CAD": 0.73, "AUD": 0.66}


def month_ends(start: dt.date, as_of: dt.date) -> pd.DatetimeIndex:
    return pd.date_range(start, as_of, freq="ME")


def make_customers(rng, n: int, start: dt.date) -> pd.DataFrame:
    seg_names = list(SEGMENTS)
    seg = rng.choice(seg_names, n, p=[SEGMENTS[s][0] for s in seg_names])
    prof_names = list(PROFILES)
    prof = rng.choice(prof_names, n, p=[PROFILES[p][0] for p in prof_names])
    country = rng.choice(list(COUNTRIES), n, p=[0.70, 0.18, 0.12])
    terms = np.array([rng.choice(SEGMENTS[s][3]) for s in seg])
    limit = np.round(np.exp(np.array([SEGMENTS[s][2] for s in seg]) + 2.0) * rng.uniform(0.8, 1.6, n), -2)
    created = pd.Timestamp(start) - pd.to_timedelta(rng.integers(0, 1500, n), unit="D")
    return pd.DataFrame({
        "customer_id": [f"C{i:06d}" for i in range(1, n + 1)],
        "customer_name": [f"Customer {i:06d}" for i in range(1, n + 1)],
        "segment": seg, "country_code": country, "currency_code": [COUNTRIES[c] for c in country],
        "payment_terms_days": terms, "credit_limit": limit, "created_at": created, "_profile": prof,
    })


def make_contacts(rng, customers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Contact phone numbers as a CRM holds them: 1-3 contacts per customer, typed in many formats.

    Planted, with the answer key in answer_key.contact_numbers (its own random stream, so the ledger is unchanged):
    - the same number typed differently across one customer's contacts (to deduplicate)
    - ~1% of customers sharing a number with another customer, e.g. one outsourced accounts office (to flag, not merge)
    - ~3% unusable entries: blanks, placeholders, too short, all one digit
    """
    def national(country):
        if country in ("US", "CA"):
            return f"{rng.integers(2, 10)}{rng.integers(0, 10)}{rng.integers(0, 10)}{rng.integers(200, 1000)}{rng.integers(0, 10000):04d}"
        return f"4{rng.integers(0, 100):02d}{rng.integers(0, 1000000):06d}" if rng.random() < 0.7 \
            else f"{rng.choice([2, 3, 7, 8])}{rng.integers(0, 100000000):08d}"

    def e164(country, nat):
        return ("+1" if country in ("US", "CA") else "+61") + nat

    def typed(country, nat):
        if country in ("US", "CA"):
            a, b, c = nat[:3], nat[3:6], nat[6:]
            forms = [f"({a}) {b}-{c}", f"{a}.{b}.{c}", f"+1 {a} {b} {c}", f"1-{a}-{b}-{c}", nat, f"001 {a} {b} {c}", f"{a}-{b}-{c} "]
        else:
            if nat[0] == "4":
                forms = [f"0{nat[:3]} {nat[3:6]} {nat[6:]}", f"+61 {nat[:3]} {nat[3:6]} {nat[6:]}", f"61{nat}", f"0{nat}"]
            else:
                forms = [f"(0{nat[0]}) {nat[1:5]} {nat[5:]}", f"+61 {nat[0]} {nat[1:5]} {nat[5:]}", f"0{nat}"]
        return forms[rng.integers(0, len(forms))]

    ids = customers["customer_id"].to_numpy()
    country = customers["country_code"].to_numpy()
    own = {cid: national(c) for cid, c in zip(ids, country)}
    sharers = rng.choice(len(ids), size=max(2, len(ids) // 100), replace=False)
    for i in sharers:  # point the customer at another customer's number in the same country
        same = np.flatnonzero(country == country[i])
        j = same[rng.integers(0, len(same))]
        if j != i:
            own[ids[i]] = own[ids[j]]
    rows, truth = [], []
    roles = ["billing", "accounts_payable", "owner"]
    for cid, c in zip(ids, country):
        n = rng.choice([1, 2, 3], p=[0.5, 0.35, 0.15])
        for k in range(n):
            contact_id = f"{cid}-{k + 1}"
            r = rng.random()
            if r < 0.03:
                raw, expected = rng.choice(["", "n/a", "000-000-0000", "12345", "TBC", "1111111111"]), None
            else:
                nat = own[cid] if (k == 0 or r < 0.75) else national(c)
                raw, expected = typed(c, nat), e164(c, nat)
            rows.append({"contact_id": contact_id, "customer_id": cid, "contact_role": roles[k], "raw_phone": raw})
            truth.append({"contact_id": contact_id, "expected_e164": expected})
    return pd.DataFrame(rows), pd.DataFrame(truth)


def make_history(rng, customers: pd.DataFrame, start: dt.date, as_of: dt.date) -> pd.DataFrame:
    """Initial row per customer plus one change for ~8% of customers (terms, segment or credit limit)."""
    base = customers[["customer_id", "customer_name", "segment", "country_code", "currency_code",
                      "payment_terms_days", "credit_limit"]].copy()
    base["updated_at"] = customers["created_at"]
    changed = customers.sample(frac=0.08, random_state=int(rng.integers(1e9))).copy()
    span = (pd.Timestamp(as_of) - pd.Timestamp(start)).days
    changed["updated_at"] = pd.Timestamp(start) + pd.to_timedelta(rng.integers(30, span, len(changed)), unit="D")
    kind = rng.choice(["terms", "segment", "limit"], len(changed))
    changed.loc[kind == "terms", "payment_terms_days"] = changed.loc[kind == "terms", "payment_terms_days"] + 15
    upgrade = {"smb": "mid_market", "mid_market": "enterprise", "enterprise": "enterprise"}
    changed.loc[kind == "segment", "segment"] = changed.loc[kind == "segment", "segment"].map(upgrade)
    changed.loc[kind == "limit", "credit_limit"] = changed.loc[kind == "limit", "credit_limit"] * 1.5
    return pd.concat([base, changed[base.columns]], ignore_index=True)


def make_invoices(rng, customers: pd.DataFrame, history: pd.DataFrame, start: dt.date, as_of: dt.date) -> pd.DataFrame:
    rows = []
    for me in month_ends(start, as_of):
        ms = me.replace(day=1)
        lam = customers["segment"].map({s: v[1] for s, v in SEGMENTS.items()}).to_numpy()
        counts = rng.poisson(lam)
        idx = np.repeat(np.arange(len(customers)), counts)
        days = rng.integers(0, me.day, len(idx))
        rows.append(pd.DataFrame({"_c": idx, "invoice_date": ms + pd.to_timedelta(days, unit="D")}))
    inv = pd.concat(rows, ignore_index=True)
    c = customers.iloc[inv["_c"]].reset_index(drop=True)
    inv["customer_id"] = c["customer_id"].to_numpy()
    inv["currency_code"] = c["currency_code"].to_numpy()
    inv["_profile"] = c["_profile"].to_numpy()

    # Terms as they stood on the invoice date (customers with a terms change get the new terms after it).
    h = history.sort_values("updated_at")
    inv = inv.sort_values("invoice_date")
    inv = pd.merge_asof(inv, h[["customer_id", "updated_at", "payment_terms_days"]],
                        left_on="invoice_date", right_on="updated_at", by="customer_id", direction="backward")
    segment_mean_log = customers.set_index("customer_id")["segment"].map({s: v[2] for s, v in SEGMENTS.items()})
    inv["amount"] = np.round(rng.lognormal(inv["customer_id"].map(segment_mean_log).to_numpy(), 0.8), 2)
    inv["due_date"] = inv["invoice_date"] + pd.to_timedelta(inv["payment_terms_days"], unit="D")
    inv = inv.sort_values(["invoice_date", "customer_id"]).reset_index(drop=True)
    inv["invoice_id"] = [f"INV{i:08d}" for i in range(1, len(inv) + 1)]
    return inv[["invoice_id", "customer_id", "invoice_date", "due_date", "currency_code", "amount", "_profile"]]


def make_credits_and_disputes(rng, inv: pd.DataFrame, as_of: pd.Timestamp):
    cn = inv.sample(frac=0.04, random_state=int(rng.integers(1e9))).copy()
    cn["issued_date"] = cn["invoice_date"] + pd.to_timedelta(rng.integers(3, 25, len(cn)), unit="D")
    cn["credit_amount"] = np.round(cn["amount"] * rng.uniform(0.05, 0.30, len(cn)), 2)
    cn["reason"] = rng.choice(["pricing_error", "service_issue", "goodwill"], len(cn))
    cn = cn[cn["issued_date"] <= as_of]
    cn = cn.assign(credit_note_id=[f"CN{i:07d}" for i in range(1, len(cn) + 1)])

    ds = inv.sample(frac=0.03, random_state=int(rng.integers(1e9))).copy()
    ds["opened_date"] = ds["invoice_date"] + pd.to_timedelta(rng.integers(5, 40, len(ds)), unit="D")
    ds["resolved_date"] = ds["opened_date"] + pd.to_timedelta(rng.integers(10, 60, len(ds)), unit="D")
    ds.loc[ds["resolved_date"] > as_of, "resolved_date"] = pd.NaT
    ds["disputed_amount"] = np.round(ds["amount"] * rng.uniform(0.2, 1.0, len(ds)), 2)
    ds = ds[ds["opened_date"] <= as_of]
    ds = ds.assign(dispute_id=[f"DS{i:07d}" for i in range(1, len(ds) + 1)])
    return (cn[["credit_note_id", "invoice_id", "issued_date", "credit_amount", "reason"]],
            ds[["dispute_id", "invoice_id", "opened_date", "resolved_date", "disputed_amount"]])


def make_payments(rng, inv: pd.DataFrame, credits: pd.DataFrame, disputes: pd.DataFrame, as_of: pd.Timestamp):
    """One or two payments per invoice; each payment is applied to its invoice, sometimes days later."""
    net = inv.set_index("invoice_id")["amount"] - credits.groupby("invoice_id")["credit_amount"].sum()
    inv = inv.assign(net=net.reindex(inv["invoice_id"]).fillna(inv.set_index("invoice_id")["amount"]).to_numpy())
    mean = inv["_profile"].map({p: v[1][0] for p, v in PROFILES.items()}).to_numpy()
    sd = inv["_profile"].map({p: v[1][1] for p, v in PROFILES.items()}).to_numpy()
    never = rng.random(len(inv)) < inv["_profile"].map({p: v[2] for p, v in PROFILES.items()}).to_numpy()
    delay = np.round(rng.normal(mean, sd)).astype(int)
    delay += np.where(inv["invoice_id"].isin(disputes["invoice_id"]), rng.integers(10, 40, len(inv)), 0)

    # 10% of invoices are paid in two instalments; the second is exactly the remainder, so cents tie.
    net_cents = np.round(inv["net"].to_numpy() * 100).astype(np.int64)
    split = rng.random(len(inv)) < 0.10
    first_cents = np.where(split, np.round(net_cents * rng.uniform(0.3, 0.7, len(inv))).astype(np.int64), net_cents)
    pays = []
    for cents, extra_days in ((first_cents, 0), (net_cents - first_cents, rng.integers(10, 45, len(inv)))):
        received = inv["due_date"] + pd.to_timedelta(delay + extra_days, unit="D")
        received = received.where(received >= inv["invoice_date"], inv["invoice_date"])
        p = pd.DataFrame({"invoice_id": inv["invoice_id"], "customer_id": inv["customer_id"],
                          "currency_code": inv["currency_code"], "received_date": received,
                          "amount": cents / 100})[~never & (cents > 0)]
        pays.append(p)
    pay = pd.concat(pays, ignore_index=True)
    pay = pay[(pay["amount"] > 0) & (pay["received_date"] <= as_of)].sort_values(["received_date", "invoice_id"])
    pay = pay.reset_index(drop=True)
    pay["payment_id"] = [f"PAY{i:08d}" for i in range(1, len(pay) + 1)]
    pay["method"] = rng.choice(["ach", "wire", "card", "check"], len(pay), p=[0.55, 0.2, 0.15, 0.1])
    pay["received_at"] = pay["received_date"] + pd.to_timedelta(rng.integers(8 * 3600, 18 * 3600, len(pay)), unit="s")
    late_load = rng.random(len(pay)) < 0.005
    pay["loaded_at"] = pay["received_at"] + pd.to_timedelta(
        np.where(late_load, rng.integers(3 * 86400, 10 * 86400, len(pay)), rng.integers(600, 7200, len(pay))), unit="s")

    lag = np.where(rng.random(len(pay)) < 0.03, rng.integers(3, 16, len(pay)), 0)
    app = pay[["payment_id", "invoice_id", "amount", "received_at", "loaded_at"]].copy()
    app["applied_at"] = app["received_at"] + pd.to_timedelta(lag, unit="D") + pd.Timedelta(hours=1)
    app = app[app["applied_at"] <= as_of + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
    app["loaded_at"] = np.maximum(app["loaded_at"], app["applied_at"] + pd.Timedelta(minutes=5))
    app = app.rename(columns={"amount": "applied_amount"}).reset_index(drop=True)
    app["application_id"] = [f"APP{i:08d}" for i in range(1, len(app) + 1)]

    payments = pay[["payment_id", "customer_id", "currency_code", "received_at", "amount", "method", "loaded_at"]]
    apps = app[["application_id", "payment_id", "invoice_id", "applied_amount", "applied_at", "loaded_at"]]
    unpaid = inv.loc[never, ["invoice_id", "due_date", "net"]]
    return payments, apps, unpaid


def make_write_offs(unpaid: pd.DataFrame, credits: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Bad-debt write-off of the full unpaid balance 180 days past due, booked as a credit note."""
    wo = unpaid.assign(issued_date=unpaid["due_date"] + pd.Timedelta(days=180))
    wo = wo[(wo["issued_date"] <= as_of) & (wo["net"] > 0)]
    start = len(credits) + 1
    return pd.DataFrame({
        "credit_note_id": [f"CN{i:07d}" for i in range(start, start + len(wo))],
        "invoice_id": wo["invoice_id"].to_numpy(), "issued_date": wo["issued_date"].to_numpy(),
        "credit_amount": np.round(wo["net"].to_numpy(), 2), "reason": "bad_debt_write_off",
    })


def make_fx(rng, start: dt.date, as_of: dt.date) -> pd.DataFrame:
    rows, level = [], dict(FX_START)
    for me in month_ends(start, as_of):
        for ccy in level:
            level[ccy] *= float(np.exp(rng.normal(0, 0.015)))
        rows += [(me.date(), ccy, round(r, 6)) for ccy, r in level.items()]
        rows.append((me.date(), "USD", 1.0))
    return pd.DataFrame(rows, columns=["month_end", "currency_code", "usd_per_unit"])


def make_gl(inv, credits, payments, start: dt.date, as_of: dt.date) -> pd.DataFrame:
    """Month-end AR control balance per currency: invoices - credit notes - cash received, cumulative."""
    cur = inv.set_index("invoice_id")["currency_code"]
    ev = pd.concat([
        pd.DataFrame({"d": inv["invoice_date"], "ccy": inv["currency_code"], "amt": inv["amount"]}),
        pd.DataFrame({"d": credits["issued_date"], "ccy": credits["invoice_id"].map(cur), "amt": -credits["credit_amount"]}),
        pd.DataFrame({"d": payments["received_at"].dt.normalize(), "ccy": payments["currency_code"], "amt": -payments["amount"]}),
    ])
    rows = []
    for me in month_ends(start, as_of):
        bal = ev[ev["d"] <= me].groupby("ccy")["amt"].sum().round(2)
        rows += [(me.date(), "1200", ccy, float(bal.get(ccy, 0.0))) for ccy in sorted(COUNTRIES.values())]
    return pd.DataFrame(rows, columns=["month_end", "account_code", "currency_code", "balance"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/receivables.duckdb")
    ap.add_argument("--customers", type=int, default=25000)
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2024, 1, 1))
    ap.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date(2025, 6, 30))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    as_of = pd.Timestamp(args.as_of)
    customers = make_customers(rng, args.customers, args.start)
    history = make_history(rng, customers, args.start, args.as_of)
    inv = make_invoices(rng, customers, history, args.start, args.as_of)
    credits, disputes = make_credits_and_disputes(rng, inv, as_of)
    payments, apps, unpaid = make_payments(rng, inv, credits, disputes, as_of)
    credits = pd.concat([credits, make_write_offs(unpaid, credits, as_of)], ignore_index=True)
    fx = make_fx(rng, args.start, args.as_of)
    gl = make_gl(inv, credits, payments, args.start, args.as_of)
    contacts, contacts_truth = make_contacts(np.random.default_rng(args.seed + 1000), customers)

    tables = {
        "customer_history": history, "invoices": inv.drop(columns=["_profile"]), "credit_notes": credits,
        "disputes": disputes, "payments": payments, "payment_applications": apps, "fx_rates_monthly": fx,
        "gl_ar_balances": gl, "customer_contacts": contacts,
    }
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(args.db) as con:
        con.execute("create schema if not exists bronze")
        for name, df in tables.items():
            con.register("df", df)
            con.execute(f"create or replace table bronze.{name} as select * from df")
            con.unregister("df")
            print(f"bronze.{name:<22} {len(df):>10,} rows")
        con.execute("create schema if not exists answer_key")
        con.register("df", contacts_truth)
        con.execute("create or replace table answer_key.contact_numbers as select * from df")
        con.unregister("df")


if __name__ == "__main__":
    main()
