select count(*) as release_count
from {{ source('raw', 'contract_notices') }}
having count(*) < 300000
