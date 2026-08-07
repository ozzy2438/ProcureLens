# Versioned demo snapshot

`procurelens-marts-v1.0.0.dump` is a PostgreSQL 16 custom-format archive used by the one-command
portfolio demo. It contains exactly 445,029 contract-grain rows and 151 agency aggregates from the
validated dbt marts.

The snapshot preserves real agency, category, procurement method, date, value and amendment
statistics. Supplier identifiers are deterministically pseudonymised, supplier names are replaced
with stable synthetic labels, free-text contract descriptions are removed, and raw OCDS payloads
are excluded. This balances a reproducible real-data demo with portfolio privacy hygiene.

The accompanying `.sha256` file is checked before every restore. `scripts/restore_snapshot.sh`
restores into a temporary schema, validates the row count, then atomically swaps it into
`analytics_marts`. Re-running the restore is safe and deterministic.

Maintainers can regenerate the archive from a validated source database with:

```bash
SOURCE_DATABASE_URL=postgresql://... make snapshot-export
```
