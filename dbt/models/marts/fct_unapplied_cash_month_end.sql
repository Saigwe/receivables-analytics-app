-- Cash received but not yet applied to an invoice, per payment per month-end.
{% set tol = var('tolerance') %}
with applied as (
    select payment_id, sum(applied_amount) as applied, max(applied_date) as last_applied_date
    from {{ ref('fct_payment_application') }}
    group by 1
),

candidates as (
    select p.payment_id, p.customer_id, p.currency_code, p.amount, m.month_end
    from {{ ref('stg_ar__payments') }} p
    left join applied a on a.payment_id = p.payment_id
    join {{ ref('dim_month') }} m
        on p.received_date <= m.month_end
        and (a.payment_id is null or a.applied < p.amount - {{ tol }} or a.last_applied_date > m.month_end)
),

unapplied as (
    select
        c.payment_id,
        c.month_end,
        c.customer_id,
        c.currency_code,
        c.amount - coalesce(sum(f.applied_amount), 0) as unapplied_amount
    from candidates c
    left join {{ ref('fct_payment_application') }} f
        on f.payment_id = c.payment_id and f.applied_date <= c.month_end
    group by 1, 2, 3, 4, c.amount
)

select
    u.*,
    cast(u.unapplied_amount * fx.usd_per_unit as decimal(18, 2)) as unapplied_usd
from unapplied u
left join {{ ref('stg_ref__fx_rates_monthly') }} fx
    on fx.month_end = u.month_end and fx.currency_code = u.currency_code
where u.unapplied_amount > {{ tol }}
