-- Every contact's standardised number must equal the answer key: the right E.164 number, or null when unusable.
select f.contact_id, f.raw_phone, f.phone_e164, k.expected_e164
from {{ ref('fct_contact_phone') }} f
join {{ source('answer_key', 'contact_numbers') }} k using (contact_id)
where f.phone_e164 is distinct from k.expected_e164
