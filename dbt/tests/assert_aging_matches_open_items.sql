-- The aging report must add up to the open-item fact at every month-end (no invoice lost in the
-- segment join to the type-2 customer dimension).
with aging as (
    select month_end, sum(open_usd) as total from {{ ref('rpt_ar_aging') }} group by 1
),

items as (
    select month_end, sum(open_usd) as total from {{ ref('fct_ar_month_end') }} group by 1
)

select i.month_end, i.total as open_items_usd, a.total as aging_usd
from items i
left join aging a on a.month_end = i.month_end
where a.total is null or abs(a.total - i.total) > 0.01
