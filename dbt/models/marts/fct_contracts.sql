-- One row per contracting process, using award-time attributes and explicit amendment tags.
with notices as (
    select * from {{ ref('stg_contract_notices') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by ocid
            order by is_amendment asc, release_date asc nulls last, release_id
        ) as release_order
    from notices
),

initial_release as (
    select * from ranked where release_order = 1
),

amendment_stats as (
    select
        notice.ocid,
        count(*) filter (where notice.is_amendment)                  as amendment_count,
        max(notice.award_value_aud) filter (where notice.is_amendment)
                                                                        as max_amended_value_aud,
        min(notice.release_date) filter (
            where notice.is_amendment
              and notice.award_value_aud > initial.award_value_aud
        )                                                              as first_upward_amendment_date,
        max(notice.release_date) filter (where notice.is_amendment)  as last_amendment_date
    from notices as notice
    inner join initial_release as initial using (ocid)
    group by notice.ocid
)

select
    initial.ocid,
    initial.release_id                                               as initial_release_id,
    initial.agency,
    initial.supplier_id,
    initial.supplier_name,
    initial.unspsc_code,
    initial.procurement_method,
    initial.contract_description,
    initial.award_date,
    initial.contract_start_date,
    initial.contract_end_date,
    initial.award_value_aud,
    initial.award_currency,
    initial.value_confidentiality,
    initial.description_confidentiality,
    coalesce(stats.amendment_count, 0)                               as amendment_count,
    stats.first_upward_amendment_date,
    stats.last_amendment_date,
    greatest(
        coalesce(stats.max_amended_value_aud, initial.award_value_aud)
            - initial.award_value_aud,
        0
    )                                                                as value_uplift_aud,
    coalesce(
        coalesce(stats.amendment_count, 0) > 0
            and stats.max_amended_value_aud > initial.award_value_aud,
        false
    )                                                                as was_amended_up
from initial_release as initial
left join amendment_stats as stats using (ocid)
