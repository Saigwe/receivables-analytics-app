-- KPI sanity: DSO is not negative, shares are proportions, CEI is a percentage.
select *
from {{ ref('rpt_ar_kpis') }}
where dso_days < 0
   or share_over_60 not between 0 and 1
   or dispute_rate < 0
   or cei_pct not between 0 and 100
