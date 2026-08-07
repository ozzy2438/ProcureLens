-- Flatten raw OCDS data at immutable release grain.
with src as (
    select * from {{ source('raw', 'contract_notices') }}
),

flattened as (
    select
        src.release_id,
        src.ocid,
        (src.payload ->> 'date')::timestamptz                         as release_date,
        coalesce(src.payload -> 'tag', '[]'::jsonb)                   as release_tags,
        coalesce(src.payload -> 'tag', '[]'::jsonb) ? 'contractAmendment'
                                                                        as is_amendment,
        coalesce(
            buyer.party ->> 'name',
            src.payload -> 'buyer' ->> 'name'
        )                                                              as agency,
        src.payload -> 'awards' -> 0 -> 'suppliers' -> 0 ->> 'id'     as supplier_id,
        src.payload -> 'awards' -> 0 -> 'suppliers' -> 0 ->> 'name'   as supplier_name,
        src.payload -> 'tender' ->> 'procurementMethod'               as procurement_method,
        src.payload -> 'contracts' -> 0 -> 'items' -> 0
            -> 'classification' ->> 'id'                              as unspsc_code,
        src.payload -> 'contracts' -> 0 ->> 'description'             as contract_description,
        (src.payload -> 'contracts' -> 0 ->> 'dateSigned')::timestamptz
                                                                        as award_date,
        (src.payload -> 'contracts' -> 0 -> 'period' ->> 'startDate')::timestamptz
                                                                        as contract_start_date,
        (src.payload -> 'contracts' -> 0 -> 'period' ->> 'endDate')::timestamptz
                                                                        as contract_end_date,
        (src.payload -> 'contracts' -> 0 -> 'value' ->> 'amount')::numeric
                                                                        as award_value_aud,
        src.payload -> 'contracts' -> 0 -> 'value' ->> 'currency'     as award_currency,
        coalesce(
            src.payload -> 'contracts' -> 0 ->> 'valueConfidentiality',
            'false'
        )                                                              as value_confidentiality,
        coalesce(
            src.payload -> 'contracts' -> 0 ->> 'descriptionConfidentiality',
            'false'
        )                                                              as description_confidentiality
    from src
    left join lateral (
        select party.value as party
        from jsonb_array_elements(
            coalesce(src.payload -> 'parties', '[]'::jsonb)
        ) as party(value)
        where party.value -> 'roles' ? 'procuringEntity'
        limit 1
    ) as buyer on true
)

select * from flattened
