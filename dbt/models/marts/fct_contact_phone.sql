-- One row per CRM contact: the phone number standardised to E.164 using the customer's country, or null with a
-- reason when it can't be used. North America: 10 digits with a leading 2-9, after an optional 1 or 001 prefix.
-- Australia: 9 national digits after a leading 0 or the 61 country code.
with contacts as (
    select
        k.*,
        c.country_code,
        regexp_replace(coalesce(k.raw_phone, ''), '[^0-9]', '', 'g') as digits
    from {{ ref('stg_ar__customer_contacts') }} k
    join {{ ref('dim_customer') }} c on c.customer_id = k.customer_id and c.is_current
),

national as (
    select
        *,
        case
            when country_code in ('US', 'CA') then
                case
                    when length(digits) = 13 and digits like '001%' then substr(digits, 4)
                    when length(digits) = 11 and digits like '1%' then substr(digits, 2)
                    when length(digits) = 10 then digits
                end
            when country_code = 'AU' then
                case
                    when length(digits) = 11 and digits like '61%' then substr(digits, 3)
                    when length(digits) = 10 and digits like '0%' then substr(digits, 2)
                    when length(digits) = 9 then digits
                end
        end as national_number
    from contacts
),

checked as (
    select
        *,
        case
            when trim(coalesce(raw_phone, '')) = '' then 'blank'
            when digits = '' then 'no digits'
            when national_number is null then 'wrong length for country'
            when length(replace(national_number, left(national_number, 1), '')) = 0 then 'placeholder'
            when country_code in ('US', 'CA') and left(national_number, 1) not in ('2', '3', '4', '5', '6', '7', '8', '9') then 'invalid area code'
            when country_code = 'AU' and left(national_number, 1) not in ('2', '3', '4', '7', '8') then 'invalid prefix'
        end as unusable_reason
    from national
)

select
    contact_id,
    customer_id,
    contact_role,
    country_code,
    raw_phone,
    case
        when unusable_reason is not null then null
        when country_code = 'AU' then '+61' || national_number
        else '+1' || national_number
    end as phone_e164,
    unusable_reason
from checked
