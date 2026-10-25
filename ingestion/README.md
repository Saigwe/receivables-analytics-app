# Ingestion

`generate_ar.py` writes a synthetic AR sub-ledger and GL into `bronze`. No public dataset has real
receivables detail, so the generator is the data source at every scale:

- **Full (default):** 25,000 customers, Jan 2024 – Jun 2025: about 660k invoices and 650k payments, in about 8 s.
- **CI:** `--customers 300 --start 2025-01-01`.

Every behaviour that makes AR hard is simulated: payer profiles, partial payments, cash applied late, credit notes, disputes, bad-debt write-offs, customer changes, and payments that load days late. The generator's docstring lists them all.
