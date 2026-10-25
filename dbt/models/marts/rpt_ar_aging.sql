-- AR aging by customer segment and bucket at as_of_date.
select
    c.segment,
    o.aging_bucket,
    count(*)                    as open_invoices,
    sum(o.open_usd)             as open_usd
from {{ ref('fct_ar_open_items') }} o
join {{ ref('stg_bronze__customers') }} c on c.customer_id = o.customer_id
where o.aging_bucket <> 'paid'
group by 1, 2
