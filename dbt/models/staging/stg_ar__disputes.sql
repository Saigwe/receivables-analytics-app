select
    dispute_id,
    invoice_id,
    cast(opened_date as date)                   as opened_date,
    cast(resolved_date as date)                 as resolved_date,
    cast(disputed_amount as decimal(18, 2))     as disputed_amount
from {{ source('bronze', 'disputes') }}
