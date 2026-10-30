-- One row per customer and distinct usable number: the deduplicated contact list collectors call from. The same
-- number typed several ways collapses to one row; the billing contact's number is the primary. A number used by
-- more than one customer (an outsourced accounts office, say) is flagged, not merged.
with numbers as (
    select
        customer_id,
        phone_e164,
        string_agg(distinct contact_role, ', ' order by contact_role)                     as contact_roles,
        count(*)                                                                           as crm_entries,
        min(case contact_role when 'billing' then 1 when 'accounts_payable' then 2 else 3 end) as role_rank
    from {{ ref('fct_contact_phone') }}
    where phone_e164 is not null
    group by 1, 2
),

shared as (
    select phone_e164, count(distinct customer_id) as customers_using
    from numbers
    group by 1
)

select
    n.customer_id,
    n.phone_e164,
    n.contact_roles,
    n.crm_entries,
    row_number() over (partition by n.customer_id order by n.role_rank, n.phone_e164) = 1 as is_primary,
    s.customers_using > 1                                                                 as is_shared_with_other_customers,
    s.customers_using
from numbers n
join shared s using (phone_e164)
