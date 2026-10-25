# Ingestion (roadmap)

Loaders for the real data go here and write to the same `bronze` tables as the fixture.

Synthetic customers, invoices and payments from a Python generator: partial payments, unapplied cash, disputes and mixed currencies. No public dataset has real AR detail, so the generator is the real-data path too. Scale it to 25k customers with `--scale`.
