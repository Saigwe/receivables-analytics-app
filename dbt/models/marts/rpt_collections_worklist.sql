-- Who to call first: customers with overdue balances at the latest month-end, ranked by money over 60
-- days past due, with credit-limit use, open disputes and how late they paid recently.
with latest as (
    select max(month_end) as month_end from {{ ref('dim_month') }}
),

open_ar as (
    select
        a.customer_id,
        sum(a.open_usd)                                                             as open_usd,
        sum(case when a.days_past_due > 0 then a.open_usd else 0 end)              as overdue_usd,
        sum(case when a.days_past_due > 60 then a.open_usd else 0 end)             as over_60_usd,
        max(a.days_past_due)                                                        as oldest_days_past_due,
        count(*)                                                                    as open_invoices
    from {{ ref('fct_ar_month_end') }} a
    join latest l on l.month_end = a.month_end
    group by 1
),

open_disputes as (
    select i.customer_id, count(*) as open_disputes
    from {{ ref('stg_ar__disputes') }} d
    join {{ ref('stg_ar__invoices') }} i on i.invoice_id = d.invoice_id
    cross join latest l
    where d.opened_date <= l.month_end and (d.resolved_date is null or d.resolved_date > l.month_end)
    group by 1
),

recent_behaviour as (
    select i.customer_id, avg(i.days_late_at_settlement) as avg_days_late_6m
    from {{ ref('fct_invoice') }} i
    cross join latest l
    where i.settled_date > {{ dbt.dateadd('month', -6, 'l.month_end') }}
    group by 1
)

select
    o.customer_id,
    c.customer_name,
    c.segment,
    c.currency_code,
    o.open_invoices,
    o.open_usd,
    o.overdue_usd,
    o.over_60_usd,
    o.oldest_days_past_due,
    o.open_usd / nullif(c.credit_limit * fx.usd_per_unit, 0)                   as credit_limit_used,
    coalesce(d.open_disputes, 0)                                                as open_disputes,
    r.avg_days_late_6m,
    rank() over (order by o.over_60_usd desc, o.overdue_usd desc, o.customer_id) as priority_rank
from open_ar o
join {{ ref('dim_customer') }} c on c.customer_id = o.customer_id and c.is_current
cross join latest l
left join {{ ref('stg_ref__fx_rates_monthly') }} fx on fx.month_end = l.month_end and fx.currency_code = c.currency_code
left join open_disputes d on d.customer_id = o.customer_id
left join recent_behaviour r on r.customer_id = o.customer_id
where o.overdue_usd > 0
