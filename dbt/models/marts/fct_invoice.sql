-- One row per invoice: credits, cash applied, what is still open, and when it was fully settled.
{% set tol = var('tolerance') %}
with credits as (
    select invoice_id, sum(credit_amount) as credited
    from {{ ref('stg_ar__credit_notes') }}
    group by 1
),

applied as (
    select invoice_id, sum(applied_amount) as applied
    from {{ ref('fct_payment_application') }}
    group by 1
),

disputes as (
    select invoice_id, count(*) as disputes, min(opened_date) as first_dispute_date
    from {{ ref('stg_ar__disputes') }}
    group by 1
),

settlement_events as (
    select invoice_id, issued_date as event_date, credit_amount as amount from {{ ref('stg_ar__credit_notes') }}
    union all
    select invoice_id, applied_date, applied_amount from {{ ref('fct_payment_application') }}
),

running as (
    select
        e.invoice_id,
        e.event_date,
        i.amount,
        sum(e.amount) over (partition by e.invoice_id order by e.event_date rows unbounded preceding) as settled_to_date
    from settlement_events e
    join {{ ref('stg_ar__invoices') }} i on i.invoice_id = e.invoice_id
),

settled as (
    select invoice_id, min(event_date) as settled_date
    from running
    where settled_to_date >= amount - {{ tol }}
    group by 1
)

select
    i.invoice_id,
    i.customer_id,
    i.invoice_date,
    i.due_date,
    cast({{ dbt.last_day('i.invoice_date', 'month') }} as date)            as invoice_month_end,
    i.currency_code,
    i.amount,
    coalesce(c.credited, 0)                                                 as credited,
    coalesce(a.applied, 0)                                                  as applied,
    i.amount - coalesce(c.credited, 0) - coalesce(a.applied, 0)             as open_amount,
    s.settled_date,
    {{ dbt.datediff('i.invoice_date', 's.settled_date', 'day') }}          as days_to_settle,
    {{ dbt.datediff('i.due_date', 's.settled_date', 'day') }}              as days_late_at_settlement,
    coalesce(d.disputes, 0) > 0                                             as is_disputed,
    d.first_dispute_date,
    fx.usd_per_unit                                                         as invoice_month_usd_rate,
    cast(i.amount * fx.usd_per_unit as decimal(18, 2))                      as amount_usd
from {{ ref('stg_ar__invoices') }} i
left join credits c on c.invoice_id = i.invoice_id
left join applied a on a.invoice_id = i.invoice_id
left join disputes d on d.invoice_id = i.invoice_id
left join settled s on s.invoice_id = i.invoice_id
left join {{ ref('stg_ref__fx_rates_monthly') }} fx
    on fx.month_end = cast({{ dbt.last_day('i.invoice_date', 'month') }} as date)
    and fx.currency_code = i.currency_code
