# Data Dictionary

## raw.contract_notices
| Column | Type | Description |
|---|---|---|
| release_id | text (PK) | Immutable OCDS release identifier |
| ocid | text (indexed) | Open Contracting ID; shared by initial and amendment releases |
| ingested_at | timestamptz | Load timestamp |
| payload | jsonb | Full OCDS release |

## marts.fct_contracts
| Column | Type | Description |
|---|---|---|
| ocid | text (PK) | Contracting process ID |
| agency | text | Buying entity name |
| supplier_name | text | Awarded supplier |
| unspsc_code | text | Category classification |
| procurement_method | text | open / limited / prequalified |
| award_date | timestamptz | First award date |
| award_value_aud | numeric | Initial award value |
| amendment_count | integer | Number of releases tagged `contractAmendment` |
| value_uplift_aud | numeric | Maximum amended value less initial award value (floored at zero) |
| first_upward_amendment_date | timestamptz | First release date at which value exceeded the initial award |
| was_amended_up | boolean | Target: later upward amendment |

## marts.dim_agencies
Rolling spend aggregates per agency (contract counts, total/avg spend, recency).
