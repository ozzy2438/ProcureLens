from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import MetaData

from procurelens.ingestion import load_historical, ocds_client


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeConnection:
    def __init__(self, rowcounts: list[int] | None = None) -> None:
        self.commands: list[str] = []
        self.rowcounts = list(rowcounts or [1])
        self.statements: list[Any] = []

    def exec_driver_sql(self, command: str) -> None:
        self.commands.append(command)

    def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.rowcounts.pop(0))


class FakeBegin:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeConnection:
        return self.connection

    def __exit__(self, *_args: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.disposed = False

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)

    def dispose(self) -> None:
        self.disposed = True


def test_ocds_raw_table_is_release_grain():
    table = ocds_client._raw_table(MetaData())
    assert table.schema == "raw"
    assert list(table.columns.keys()) == ["release_id", "ocid", "ingested_at", "payload"]
    assert table.c.release_id.primary_key is True


def test_release_grain_bootstrap_executes_schema_table_migration_and_index_blocks():
    connection = FakeConnection()
    ocds_client._ensure_release_grain(connection)
    assert len(connection.commands) == 4
    assert "create schema if not exists raw" in connection.commands[0]
    assert "primary key" in connection.commands[1].lower()
    assert "Cannot migrate" in connection.commands[2]
    assert "ix_contract_notices_ocid" in connection.commands[3]


def test_fetch_contract_notices_follows_relative_pagination(monkeypatch):
    pages = [
        {"releases": [{"id": "r1"}], "links": {"next": "/ocds/page-2"}},
        {"releases": [{"id": "r2"}], "links": {}},
    ]
    requested: list[str] = []

    class Response:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return self.payload

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["headers"]["User-Agent"].startswith("ProcureLens/")

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, url: str) -> Response:
            requested.append(url)
            return Response(pages.pop(0))

    monkeypatch.setattr(ocds_client.httpx, "HTTPTransport", lambda **_kwargs: object())
    monkeypatch.setattr(ocds_client.httpx, "Client", Client)
    releases = ocds_client.fetch_contract_notices(date(2025, 1, 1), date(2025, 1, 2))
    assert [release["id"] for release in releases] == ["r1", "r2"]
    assert requested[1] == "https://api.tenders.gov.au/ocds/page-2"


def test_land_raw_is_idempotent_release_grain_and_skips_invalid_rows(monkeypatch):
    connection = FakeConnection([2])
    engine = FakeEngine(connection)
    monkeypatch.setattr(ocds_client, "create_engine", lambda *_args, **_kwargs: engine)
    inserted = ocds_client.land_raw(
        [
            {"id": "release-1", "ocid": "ocid-1", "value": 1},
            {"id": "release-2", "ocid": "ocid-1", "value": 2},
            {"id": "missing-ocid"},
            {"ocid": "missing-id"},
        ],
        "postgresql://example",
    )
    assert inserted == 2
    assert len(connection.statements) == 1
    assert "ON CONFLICT (release_id) DO NOTHING" in str(connection.statements[0])
    assert engine.disposed is True


def test_land_raw_short_circuits_empty_or_entirely_invalid_batches():
    assert ocds_client.land_raw([]) == 0
    assert ocds_client.land_raw([{"id": "missing-ocid"}]) == 0


def test_ocds_cli_chunks_inclusive_date_range(monkeypatch):
    fetched: list[tuple[date, date]] = []
    landed: list[list[dict[str, str]]] = []

    def fake_fetch(start: date, end: date) -> list[dict[str, str]]:
        fetched.append((start, end))
        return [{"id": start.isoformat(), "ocid": "x"}]

    def fake_land(rows: list[dict[str, str]]) -> int:
        landed.append(rows)
        return len(rows)

    monkeypatch.setattr(ocds_client, "fetch_contract_notices", fake_fetch)
    monkeypatch.setattr(ocds_client, "land_raw", fake_land)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ocds_client",
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-05",
            "--chunk-days",
            "2",
        ],
    )
    ocds_client.main()
    assert fetched == [
        (date(2025, 1, 1), date(2025, 1, 2)),
        (date(2025, 1, 3), date(2025, 1, 4)),
        (date(2025, 1, 5), date(2025, 1, 5)),
    ]
    assert len(landed) == 3


@pytest.mark.parametrize(
    "args",
    [
        ["ocds_client", "--start", "2025-01-02", "--end", "2025-01-01"],
        ["ocds_client", "--start", "2025-01-01", "--end", "2025-01-02", "--chunk-days", "0"],
        ["ocds_client"],
    ],
)
def test_ocds_cli_rejects_invalid_ranges(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit):
        ocds_client.main()


def test_historical_column_normalisation_and_table_contract():
    assert load_historical._normalise_column(" Contract ID ($) ") == "contract_id"
    table = load_historical._history_table(MetaData())
    assert table.schema == "raw"
    assert table.c.row_hash.primary_key is True


class FakeHistoryTable:
    def __init__(self) -> None:
        self.created = False

    def create(self, _connection: Any, *, checkfirst: bool) -> None:
        self.created = checkfirst


class FakeInsert:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.conflict_columns: list[str] = []

    def values(self, rows: list[dict[str, Any]]) -> FakeInsert:
        self.rows = rows
        return self

    def on_conflict_do_nothing(self, *, index_elements: list[str]) -> FakeInsert:
        self.conflict_columns = index_elements
        return self


def test_historical_loader_hashes_normalised_rows_and_is_idempotent(tmp_path: Path, monkeypatch):
    source = tmp_path / "Historical Contracts.csv"
    source.write_text("placeholder", encoding="utf-8")
    frame = pd.DataFrame(
        [
            {"Contract ID": "CN-1", "Agency Name": "Finance"},
            {"Contract ID": "CN-2", "Agency Name": "Defence"},
        ]
    )
    history = FakeHistoryTable()
    statements: list[FakeInsert] = []
    connection = FakeConnection([2])
    engine = FakeEngine(connection)

    def fake_insert(_table: Any) -> FakeInsert:
        statement = FakeInsert()
        statements.append(statement)
        return statement

    monkeypatch.setattr(load_historical, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(load_historical, "_history_table", lambda _metadata: history)
    monkeypatch.setattr(load_historical, "insert", fake_insert)
    monkeypatch.setattr(load_historical.pd, "read_csv", lambda *_args, **_kwargs: iter([frame]))

    assert load_historical.load_csv_dump(str(source), "postgresql://example") == 2
    assert history.created is True
    assert statements[0].conflict_columns == ["row_hash"]
    assert [row["contract_id"] for row in statements[0].rows] == ["CN-1", "CN-2"]
    assert all(len(row["row_hash"]) == 64 for row in statements[0].rows)
    assert statements[0].rows[0]["payload"] == {
        "contract_id": "CN-1",
        "agency_name": "Finance",
    }
    assert engine.disposed is True


def test_historical_loader_rejects_missing_path(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_historical.load_csv_dump(str(tmp_path / "missing.csv"))


def test_historical_cli_sums_multiple_files(monkeypatch):
    calls: list[str] = []

    def fake_load(path: str) -> int:
        calls.append(path)
        return 2

    monkeypatch.setattr(load_historical, "load_csv_dump", fake_load)
    monkeypatch.setattr(sys, "argv", ["load_historical", "a.csv", "b.csv"])
    load_historical.main()
    assert calls == ["a.csv", "b.csv"]
