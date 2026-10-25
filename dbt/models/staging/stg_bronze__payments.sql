select
    payment_id,
    invoice_id,
    cast(payment_date as date)           as payment_date,
    amount_usd
from {{ source('bronze', 'payments') }}
