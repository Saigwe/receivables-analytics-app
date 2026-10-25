-- One row per invoice issued by as_of_date, with its open balance and aging bucket at that date.
{% set as_of = "cast('" ~ var('as_of_date') ~ "' as date)" %}
with paid as (
    select invoice_id, sum(amount_usd) as paid_usd
    from {{ ref('stg_bronze__payments') }}
    where payment_date <= {{ as_of }}
    group by 1
)

select
    i.invoice_id,
    i.customer_id,
    i.invoice_date,
    i.due_date,
    i.amount_usd,
    coalesce(p.paid_usd, 0)                                 as paid_usd,
    i.amount_usd - coalesce(p.paid_usd, 0)                  as open_usd,
    {{ dbt.datediff('i.due_date', as_of, 'day') }}          as days_past_due,
    case
        when i.amount_usd - coalesce(p.paid_usd, 0) <= 0 then 'paid'
        when {{ dbt.datediff('i.due_date', as_of, 'day') }} <= 0 then 'current'
        when {{ dbt.datediff('i.due_date', as_of, 'day') }} <= 30 then '1-30'
        when {{ dbt.datediff('i.due_date', as_of, 'day') }} <= 60 then '31-60'
        when {{ dbt.datediff('i.due_date', as_of, 'day') }} <= 90 then '61-90'
        else '90+'
    end                                                     as aging_bucket
from {{ ref('stg_bronze__invoices') }} i
left join paid p on p.invoice_id = i.invoice_id
where i.invoice_date <= {{ as_of }}
