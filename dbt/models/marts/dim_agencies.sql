-- Agency dimension at one-contract-per-ocid grain (amendment releases are not double counted).
select
    agency,
    count(*)                                as contracts_all_time,
    sum(award_value_aud)                    as total_spend_aud,
    avg(award_value_aud)                    as avg_contract_aud,
    max(award_date)                         as last_award_date
from {{ ref('fct_contracts') }}
where agency is not null
group by agency
