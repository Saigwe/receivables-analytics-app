select
    cast(month_end as date)                 as month_end,
    currency_code,
    cast(usd_per_unit as decimal(18, 6))    as usd_per_unit
from {{ source('bronze', 'fx_rates_monthly') }}
