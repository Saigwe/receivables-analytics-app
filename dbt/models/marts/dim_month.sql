-- The month-ends the ledger closes on (one row per month-end in the GL).
select distinct month_end
from {{ ref('stg_gl__ar_balances') }}
