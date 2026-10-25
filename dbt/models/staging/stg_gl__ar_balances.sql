select
    cast(month_end as date)             as month_end,
    account_code,
    currency_code,
    cast(balance as decimal(18, 2))     as balance
from {{ source('bronze', 'gl_ar_balances') }}
