select
    contact_id,
    customer_id,
    contact_role,
    raw_phone
from {{ source('bronze', 'customer_contacts') }}
