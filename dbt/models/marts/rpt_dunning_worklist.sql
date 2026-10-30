-- Who to chase, and how, at the latest month-end. Positive-debt targeting: a customer is chased only when their
-- overdue, undisputed balance is more than their unapplied cash, so nobody is reminded about money they've already
-- paid or are disputing. The tranche follows the oldest chaseable invoice; a call needs a usable number.
--   T1  1-30 days past due   reminder e-mail
--   T2  31-60                phone call
--   T3  61-90                final notice
--   T4  over 90              escalate (pre-collections review)
with latest as (
    select max(month_end) as month_end from {{ ref('dim_month') }}
),

disputed as (
    select distinct d.invoice_id
    from {{ ref('stg_ar__disputes') }} d
    cross join latest l
    where d.opened_date <= l.month_end and (d.resolved_date is null or d.resolved_date > l.month_end)
),

overdue as (
    select
        a.customer_id,
        sum(a.open_usd)                                                         as overdue_usd,
        sum(case when x.invoice_id is null then a.open_usd else 0 end)          as chaseable_usd,
        sum(case when x.invoice_id is not null then a.open_usd else 0 end)      as disputed_usd,
        max(case when x.invoice_id is null then a.days_past_due end)            as oldest_chaseable_days
    from {{ ref('fct_ar_month_end') }} a
    join latest l on l.month_end = a.month_end
    left join disputed x on x.invoice_id = a.invoice_id
    where a.days_past_due > 0
    group by 1
),

unapplied as (
    select u.customer_id, sum(u.unapplied_usd) as unapplied_usd
    from {{ ref('fct_unapplied_cash_month_end') }} u
    join latest l on l.month_end = u.month_end
    group by 1
),

primary_phone as (
    select customer_id, phone_e164, is_shared_with_other_customers
    from {{ ref('dim_customer_phone') }}
    where is_primary
),

scored as (
    select
        o.customer_id,
        o.overdue_usd,
        o.disputed_usd,
        coalesce(u.unapplied_usd, 0)                                    as unapplied_usd,
        o.chaseable_usd - coalesce(u.unapplied_usd, 0)                  as net_chaseable_usd,
        o.oldest_chaseable_days
    from overdue o
    left join unapplied u using (customer_id)
)

select
    s.customer_id,
    c.customer_name,
    c.segment,
    c.currency_code,
    s.overdue_usd,
    s.disputed_usd,
    s.unapplied_usd,
    s.net_chaseable_usd,
    s.oldest_chaseable_days,
    case
        when s.oldest_chaseable_days <= 30 then 'T1'
        when s.oldest_chaseable_days <= 60 then 'T2'
        when s.oldest_chaseable_days <= 90 then 'T3'
        else 'T4'
    end                                                                         as tranche,
    case
        when s.oldest_chaseable_days <= 30 then 'reminder e-mail'
        when s.oldest_chaseable_days <= 60 and p.phone_e164 is not null then 'phone call'
        when s.oldest_chaseable_days <= 60 then 'e-mail (no usable number)'
        when s.oldest_chaseable_days <= 90 then 'final notice'
        else 'escalate'
    end                                                                         as action,
    p.phone_e164                                                                as primary_phone,
    coalesce(p.is_shared_with_other_customers, false)                           as phone_shared_with_other_customers,
    rank() over (order by s.net_chaseable_usd desc, s.customer_id)              as priority_rank
from scored s
join {{ ref('dim_customer') }} c on c.customer_id = s.customer_id and c.is_current
left join primary_phone p on p.customer_id = s.customer_id
where s.net_chaseable_usd > {{ var('tolerance') }}
  and s.oldest_chaseable_days is not null
