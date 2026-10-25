select
    invoice_id,
    customer_id,
    cast(invoice_date as date)           as invoice_date,
    cast(due_date as date)               as due_date,
    amount_usd
from {{ source('bronze', 'invoices') }}
