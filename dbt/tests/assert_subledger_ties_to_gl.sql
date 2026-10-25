-- The audit claim: every month-end and currency, net AR in the sub-ledger equals the GL control account.
select * from {{ ref('rpt_ledger_tie') }} where not is_tied
