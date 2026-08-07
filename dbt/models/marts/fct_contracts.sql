-- One row per contract with amendment outcome (model training grain).
with notices as (
    select * from {{ ref('stg_contract_notices') }}
),

amendments as (
    -- releases sharing an ocid after the first award are amendments
    select
        ocid,
        count(*) - 1                                   as amendment_count,
        max(award_value_aud) - min(award_value_aud)    as value_uplift_aud
    from notices
    group by ocid
)

select
    n.ocid,
    n.agency,
    n.supplier_name,
    n.unspsc_code,
    n.procurement_method,
    n.award_date,
    n.award_value_aud,
    coalesce(a.amendment_count, 0) > 0
        and coalesce(a.value_uplift_aud, 0) > 0        as was_amended_up
from notices n
left join amendments a using (ocid)
