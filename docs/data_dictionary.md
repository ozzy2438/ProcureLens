# Data Dictionary

## raw.contract_notices
| Column | Type | Description |
|---|---|---|
| ocid | text (PK) | Open Contracting ID for the contracting process |
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
| was_amended_up | boolean | Target: later upward amendment |

## marts.dim_agencies
Rolling spend aggregates per agency (contract counts, total/avg spend, recency).
