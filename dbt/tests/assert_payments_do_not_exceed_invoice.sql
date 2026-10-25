-- Cash applied to an invoice can never exceed the invoice amount.
select invoice_id, amount_usd, paid_usd
from {{ ref('fct_ar_open_items') }}
where paid_usd > amount_usd + 0.005
