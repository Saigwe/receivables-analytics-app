-- Month-end receivables KPIs in USD.
--   DSO  = net AR / credit sales of the last 3 months x days in those months
--   CEI  = (opening AR + sales - closing AR) / (opening AR + sales - closing current AR) x 100
--          (collection effectiveness index; 100 = everything collectable was collected)
with ar as (
    select
        month_end,
        sum(open_usd)                                                               as ar_open_usd,
        sum(case when aging_bucket = 'current' then open_usd else 0 end)            as ar_current_usd,
        sum(case when aging_bucket in ('61-90', '91-120', '120+') then open_usd else 0 end) as ar_over_60_usd
    from {{ ref('fct_ar_month_end') }}
    group by 1
),

unapplied as (
    select month_end, sum(unapplied_usd) as unapplied_usd
    from {{ ref('fct_unapplied_cash_month_end') }}
    group by 1
),

sales as (
    select
        invoice_month_end                           as month_end,
        count(*)                                    as invoices_issued,
        sum(amount_usd)                             as sales_usd
    from {{ ref('fct_invoice') }}
    group by 1
),

settled as (
    select cast({{ dbt.last_day('settled_date', 'month') }} as date) as month_end,
           avg(days_to_settle) as avg_days_to_settle
    from {{ ref('fct_invoice') }}
    where settled_date is not null
    group by 1
),

write_offs as (
    select
        cast({{ dbt.last_day('c.issued_date', 'month') }} as date)    as month_end,
        sum(c.credit_amount * fx.usd_per_unit)                         as write_offs_usd
    from {{ ref('stg_ar__credit_notes') }} c
    join {{ ref('stg_ar__invoices') }} i on i.invoice_id = c.invoice_id
    join {{ ref('stg_ref__fx_rates_monthly') }} fx
        on fx.month_end = cast({{ dbt.last_day('c.issued_date', 'month') }} as date)
        and fx.currency_code = i.currency_code
    where c.reason = 'bad_debt_write_off'
    group by 1
),

disputes as (
    select cast({{ dbt.last_day('opened_date', 'month') }} as date) as month_end, count(*) as disputes_opened
    from {{ ref('stg_ar__disputes') }}
    group by 1
),

base as (
    select
        m.month_end,
        coalesce(ar.ar_open_usd, 0)                                     as ar_open_usd,
        coalesce(ar.ar_current_usd, 0)                                  as ar_current_usd,
        coalesce(ar.ar_over_60_usd, 0)                                  as ar_over_60_usd,
        coalesce(u.unapplied_usd, 0)                                    as unapplied_usd,
        coalesce(s.sales_usd, 0)                                        as sales_usd,
        coalesce(s.invoices_issued, 0)                                  as invoices_issued,
        coalesce(d.disputes_opened, 0)                                  as disputes_opened,
        coalesce(w.write_offs_usd, 0)                                   as write_offs_usd,
        st.avg_days_to_settle,
        lag(coalesce(ar.ar_open_usd, 0)) over (order by m.month_end)    as opening_ar_usd,
        sum(coalesce(s.sales_usd, 0)) over (order by m.month_end rows between 2 preceding and current row) as sales_3m_usd,
        count(*) over (order by m.month_end rows between 2 preceding and current row) as months_in_window
    from {{ ref('dim_month') }} m
    left join ar on ar.month_end = m.month_end
    left join unapplied u on u.month_end = m.month_end
    left join sales s on s.month_end = m.month_end
    left join settled st on st.month_end = m.month_end
    left join disputes d on d.month_end = m.month_end
    left join write_offs w on w.month_end = m.month_end
)

select
    month_end,
    ar_open_usd,
    unapplied_usd,
    ar_open_usd - unapplied_usd                                             as net_ar_usd,
    sales_usd,
    invoices_issued,
    case when months_in_window = 3 and sales_3m_usd > 0
         then (ar_open_usd - unapplied_usd) / sales_3m_usd
              * {{ dbt.datediff(dbt.dateadd('month', -3, 'month_end'), 'month_end', 'day') }}
    end                                                                     as dso_days,
    case when opening_ar_usd is not null
         then 100.0 * (opening_ar_usd + sales_usd - ar_open_usd)
              / nullif(opening_ar_usd + sales_usd - ar_current_usd, 0)
    end                                                                     as cei_pct,
    ar_over_60_usd / nullif(ar_open_usd, 0)                                 as share_over_60,
    cast(disputes_opened as double) / nullif(invoices_issued, 0)            as dispute_rate,
    write_offs_usd,
    avg_days_to_settle
from base
