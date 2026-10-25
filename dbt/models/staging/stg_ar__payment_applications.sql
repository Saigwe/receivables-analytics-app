select
    application_id,
    payment_id,
    invoice_id,
    cast(applied_amount as decimal(18, 2))  as applied_amount,
    cast(applied_at as timestamp)           as applied_at,
    cast(applied_at as date)                as applied_date,
    cast(loaded_at as timestamp)            as loaded_at
from {{ source('bronze', 'payment_applications') }}
where loaded_at <= cast('{{ var("load_cutoff") }}' as timestamp)
