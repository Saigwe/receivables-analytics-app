-- Nobody is chased for money they've already paid (unapplied cash) or are disputing, every chased customer really
-- has overdue undisputed debt, and nobody is booked for a call without a usable number.
select customer_id, net_chaseable_usd, disputed_usd, unapplied_usd, action, primary_phone
from {{ ref('rpt_dunning_worklist') }}
where net_chaseable_usd <= 0
   or net_chaseable_usd > overdue_usd - disputed_usd + 0.01
   or (action = 'phone call' and primary_phone is null)
