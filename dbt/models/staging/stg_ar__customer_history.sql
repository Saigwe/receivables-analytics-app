select
    customer_id,
    customer_name,
    segment,
    country_code,
    currency_code,
    cast(payment_terms_days as integer)     as payment_terms_days,
    cast(credit_limit as decimal(18, 2))    as credit_limit,
    cast(updated_at as date)                as valid_from
from {{ source('bronze', 'customer_history') }}
