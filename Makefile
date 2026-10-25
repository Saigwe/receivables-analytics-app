PY ?= python
DB ?= warehouse/receivables.duckdb
FIXTURE_DB ?= warehouse/fixture.duckdb
DBT = cd dbt && DUCKDB_PATH=../$(DB) dbt

.PHONY: all fixture-all bronze bronze-fixture dbt record incremental-check app clean

all: bronze dbt record incremental-check                   ## 25k customers, Jan 2024 - Jun 2025
fixture-all:                                               ## 300 customers, 6 months (CI)
	$(MAKE) bronze-fixture dbt record incremental-check DB=$(FIXTURE_DB)
	$(PY) -m py_compile app/streamlit_app.py

bronze:
	$(PY) ingestion/generate_ar.py --db $(DB)

bronze-fixture:
	$(PY) ingestion/generate_ar.py --db $(DB) --customers 300 --start 2025-01-01

dbt:
	$(DBT) build --profiles-dir .

record:
	$(PY) scripts/record_run.py --db $(DB)

incremental-check:
	$(PY) scripts/check_incremental.py --db $(DB) --cutoff "2025-03-15 00:00:00"

app:
	AR_DUCKDB_PATH=$(CURDIR)/$(DB) streamlit run app/streamlit_app.py

clean:
	rm -rf warehouse dbt/target dbt/logs
