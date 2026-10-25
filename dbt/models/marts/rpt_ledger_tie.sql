-- Does the sub-ledger tie to the GL? Net AR = open invoices - unapplied cash, per currency and month-end,
-- against the AR control account (1200). The app shows this as its "ties to ledger" banner.
{% set tol = var('tolerance') %}
with open_items as (
    select month_end, currency_code, sum(open_amount) as open_items
    from {{ ref('fct_ar_month_end') }}
    group by 1, 2
),

unapplied as (
    select month_end, currency_code, sum(unapplied_amount) as unapplied_cash
    from {{ ref('fct_unapplied_cash_month_end') }}
    group by 1, 2
)

select
    g.month_end,
    g.currency_code,
    coalesce(o.open_items, 0)                                               as open_items,
    coalesce(u.unapplied_cash, 0)                                           as unapplied_cash,
    coalesce(o.open_items, 0) - coalesce(u.unapplied_cash, 0)               as subledger_net_ar,
    g.balance                                                               as gl_balance,
    g.balance - (coalesce(o.open_items, 0) - coalesce(u.unapplied_cash, 0)) as variance,
    abs(g.balance - (coalesce(o.open_items, 0) - coalesce(u.unapplied_cash, 0))) < 0.01 as is_tied
from {{ ref('stg_gl__ar_balances') }} g
left join open_items o on o.month_end = g.month_end and o.currency_code = g.currency_code
left join unapplied u on u.month_end = g.month_end and u.currency_code = g.currency_code
where g.account_code = '1200'
