with expected_years as (
    select generate_series(2019, 2025) as award_year
),

observed_years as (
    select distinct extract(year from award_date)::integer as award_year
    from {{ ref('fct_contracts') }}
)

select expected.award_year
from expected_years as expected
left join observed_years as observed using (award_year)
where observed.award_year is null
