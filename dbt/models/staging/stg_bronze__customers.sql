select
    customer_id,
    customer_name,
    segment,
    payment_terms_days
from {{ source('bronze', 'customers') }}
