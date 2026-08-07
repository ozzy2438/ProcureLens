-- Agency dimension with rolling spend aggregates for the fit scorer.
select
    agency,
    count(*)                                as contracts_all_time,
    sum(award_value_aud)                    as total_spend_aud,
    avg(award_value_aud)                    as avg_contract_aud,
    max(award_date)                         as last_award_date
from {{ ref('stg_contract_notices') }}
group by agency
