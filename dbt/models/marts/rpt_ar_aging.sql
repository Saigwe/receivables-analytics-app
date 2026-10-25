-- AR aging in USD by month-end, customer segment (as it was at that month-end) and bucket.
select
    a.month_end,
    c.segment,
    a.aging_bucket,
    count(*)                    as open_invoices,
    count(distinct a.customer_id) as customers,
    sum(a.open_usd)             as open_usd
from {{ ref('fct_ar_month_end') }} a
join {{ ref('dim_customer') }} c
    on c.customer_id = a.customer_id
    and a.month_end between c.valid_from and c.valid_to
group by 1, 2, 3
