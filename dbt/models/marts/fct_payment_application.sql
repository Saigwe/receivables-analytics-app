{{
    config(
        materialized='incremental',
        unique_key='application_id',
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}
-- One row per cash application (payment applied to an invoice). Incremental on load time, so
-- payments that load days late are still picked up.
with apps as (
    select *
    from {{ ref('stg_ar__payment_applications') }}
    {% if is_incremental() %}
    where loaded_at > (
        select {{ dbt.dateadd('day', -1 * var('lookback_days'), 'max(loaded_at)') }} from {{ this }}
    )
    {% endif %}
)

select
    a.application_id,
    a.payment_id,
    a.invoice_id,
    i.customer_id,
    i.currency_code,
    a.applied_amount,
    a.applied_at,
    a.applied_date,
    p.received_at,
    p.received_date,
    {{ dbt.datediff('p.received_date', 'a.applied_date', 'day') }}    as application_lag_days,
    a.loaded_at
from apps a
join {{ ref('stg_ar__invoices') }} i on i.invoice_id = a.invoice_id
left join {{ ref('stg_ar__payments') }} p on p.payment_id = a.payment_id
