select
    payment_id,
    customer_id,
    currency_code,
    cast(received_at as timestamp)      as received_at,
    cast(received_at as date)           as received_date,
    cast(amount as decimal(18, 2))      as amount,
    method,
    cast(loaded_at as timestamp)        as loaded_at
from {{ source('bronze', 'payments') }}
-- Simulates what had landed by a given load time (see `make incremental-check`).
where loaded_at <= cast('{{ var("load_cutoff") }}' as timestamp)
