select
    credit_note_id,
    invoice_id,
    cast(issued_date as date)               as issued_date,
    cast(credit_amount as decimal(18, 2))   as credit_amount,
    reason
from {{ source('bronze', 'credit_notes') }}
