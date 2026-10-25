-- Cash can't be applied before it arrives, a payment can't be applied beyond its amount,
-- and an invoice can't be settled beyond its amount.
select application_id as id, 'applied before received' as problem
from {{ ref('fct_payment_application') }}
where applied_date < received_date

union all

select p.payment_id, 'payment over-applied'
from {{ ref('stg_ar__payments') }} p
join {{ ref('fct_payment_application') }} a on a.payment_id = p.payment_id
group by p.payment_id, p.amount
having sum(a.applied_amount) > p.amount + {{ var('tolerance') }}

union all

select invoice_id, 'invoice over-settled'
from {{ ref('fct_invoice') }}
where credited + applied > amount + {{ var('tolerance') }}
