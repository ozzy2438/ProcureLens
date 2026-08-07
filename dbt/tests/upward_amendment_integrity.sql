select
    ocid,
    amendment_count,
    award_value_aud,
    value_uplift_aud,
    first_upward_amendment_date
from {{ ref('fct_contracts') }}
where was_amended_up
  and (
      amendment_count < 1
      or value_uplift_aud <= 0
      or first_upward_amendment_date is null
  )
