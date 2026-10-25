-- One row per invoice per month-end while it is open: the open balance and aging bucket at that
-- month-end. Open = invoice amount - credits issued - cash applied, each up to the month-end.
{% set tol = var('tolerance') %}
with events as (
    select invoice_id, invoice_date as event_date, amount as delta from {{ ref('stg_ar__invoices') }}
    union all
    select invoice_id, issued_date, -credit_amount from {{ ref('stg_ar__credit_notes') }}
    union all
    select invoice_id, applied_date, -applied_amount from {{ ref('fct_payment_application') }}
),

monthly as (
    select invoice_id, cast({{ dbt.last_day('event_date', 'month') }} as date) as month_end, sum(delta) as delta
    from events
    group by 1, 2
),

-- Month-ends from the invoice's month until the month it was settled (exclusive).
span as (
    select i.invoice_id, m.month_end
    from {{ ref('fct_invoice') }} i
    join {{ ref('dim_month') }} m
        on m.month_end >= i.invoice_month_end
        and (i.settled_date is null or m.month_end < cast({{ dbt.last_day('i.settled_date', 'month') }} as date))
),

balances as (
    select
        s.invoice_id,
        s.month_end,
        sum(coalesce(m.delta, 0)) over (partition by s.invoice_id order by s.month_end rows unbounded preceding) as open_amount
    from span s
    left join monthly m on m.invoice_id = s.invoice_id and m.month_end = s.month_end
)

select
    b.invoice_id,
    b.month_end,
    i.customer_id,
    i.currency_code,
    i.invoice_date,
    i.due_date,
    b.open_amount,
    cast(b.open_amount * fx.usd_per_unit as decimal(18, 2))             as open_usd,
    {{ dbt.datediff('i.due_date', 'b.month_end', 'day') }}             as days_past_due,
    {{ aging_bucket(dbt.datediff('i.due_date', 'b.month_end', 'day')) }} as aging_bucket
from balances b
join {{ ref('fct_invoice') }} i on i.invoice_id = b.invoice_id
left join {{ ref('stg_ref__fx_rates_monthly') }} fx
    on fx.month_end = b.month_end and fx.currency_code = i.currency_code
where b.open_amount > {{ tol }}
