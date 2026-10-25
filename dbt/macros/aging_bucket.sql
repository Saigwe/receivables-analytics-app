{# Standard AR aging buckets from days past due (negative or zero = not yet due). #}
{% macro aging_bucket(days_past_due) -%}
    case
        when {{ days_past_due }} <= 0 then 'current'
        when {{ days_past_due }} <= 30 then '1-30'
        when {{ days_past_due }} <= 60 then '31-60'
        when {{ days_past_due }} <= 90 then '61-90'
        when {{ days_past_due }} <= 120 then '91-120'
        else '120+'
    end
{%- endmacro %}
