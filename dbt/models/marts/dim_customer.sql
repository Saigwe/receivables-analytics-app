-- Type-2 customer dimension: one row per customer version, valid from its change date until the day
-- before the next change. Reports join on the month-end to use the segment and terms as they were then.
select
    customer_id || '-' || cast(valid_from as varchar)                       as customer_version_key,
    customer_id,
    customer_name,
    segment,
    country_code,
    currency_code,
    payment_terms_days,
    credit_limit,
    valid_from,
    coalesce(
        {{ dbt.dateadd('day', -1, 'lead(valid_from) over w') }},
        cast('9999-12-31' as date)
    )                                                                       as valid_to,
    lead(valid_from) over w is null                                         as is_current
from {{ ref('stg_ar__customer_history') }}
window w as (partition by customer_id order by valid_from)
