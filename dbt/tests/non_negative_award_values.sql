select ocid, award_value_aud
from {{ ref('fct_contracts') }}
where award_value_aud < 0
