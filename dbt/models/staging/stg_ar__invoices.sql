select
    invoice_id,
    customer_id,
    cast(invoice_date as date)          as invoice_date,
    cast(due_date as date)              as due_date,
    currency_code,
    cast(amount as decimal(18, 2))      as amount
from {{ source('bronze', 'invoices') }}
