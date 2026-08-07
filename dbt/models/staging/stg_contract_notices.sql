-- Flatten raw OCDS releases into typed columns.
with src as (
    select * from {{ source('raw', 'contract_notices') }}
)

select
    ocid,
    payload ->> 'id'                                            as release_id,
    (payload -> 'tender' ->> 'title')                           as tender_title,
    (payload -> 'buyer' ->> 'name')                             as agency,
    (payload -> 'awards' -> 0 -> 'value' ->> 'amount')::numeric as award_value_aud,
    (payload -> 'awards' -> 0 ->> 'date')::timestamptz          as award_date,
    (payload -> 'tender' ->> 'procurementMethod')               as procurement_method,
    (payload -> 'tender' -> 'items' -> 0 -> 'classification'
        ->> 'id')                                               as unspsc_code,
    (payload -> 'awards' -> 0 -> 'suppliers' -> 0 ->> 'name')   as supplier_name
from src
