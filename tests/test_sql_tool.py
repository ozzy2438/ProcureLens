from __future__ import annotations

from typing import Any, cast

import pytest

from procurelens.agent.tools.sql_tool import (
    SafeSQLTool,
    UnsafeQueryError,
    plan_nl_query,
    validate_select_query,
)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM analytics_marts.fct_contracts",
        "SELECT * FROM raw.contract_notices",
        "SELECT * FROM fct_contracts",
        "SELECT * FROM analytics_marts.unknown_mart",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT 1; SELECT 2",
    ],
)
def test_sql_validator_rejects_unsafe_or_out_of_scope_queries(query: str):
    with pytest.raises(UnsafeQueryError):
        validate_select_query(query)


def test_sql_validator_accepts_select_with_cte_on_allowlisted_mart():
    query = """
        WITH agency_contracts AS (
            SELECT agency, award_value_aud
            FROM analytics_marts.fct_contracts
        )
        SELECT agency, SUM(award_value_aud) AS spend
        FROM agency_contracts
        GROUP BY agency
    """
    validated = validate_select_query(query)
    assert validated.startswith("WITH agency_contracts AS")
    assert "analytics_marts.fct_contracts" in validated


@pytest.mark.parametrize(
    ("question", "context", "intent"),
    [
        ("Show contract spend", {"agency": "Finance"}, "spend"),
        ("Show incumbent suppliers", {"agency": "Finance"}, "suppliers"),
        ("Show amendment uplift", {"agency": "Finance"}, "amendments"),
    ],
)
def test_reviewed_query_planner_selects_expected_intent(question, context, intent):
    plan = plan_nl_query(question, context)
    assert plan.intent == intent
    assert plan.params["agency_pattern"] == "%Finance%"
    assert "analytics_marts." in plan.query


def test_query_planner_binds_and_caps_requested_supplier_limit():
    from_question = plan_nl_query("Show the top 5 suppliers", {"agency": "Finance"})
    from_context = plan_nl_query(
        "Show incumbent suppliers", {"agency": "Finance", "limit": 999}
    )
    assert from_question.params["requested_limit"] == 5
    assert from_context.params["requested_limit"] == 50
    assert "LIMIT :requested_limit" in from_question.query


class FakeTransaction:
    def __init__(self) -> None:
        self.rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True


class FakeMappings:
    def all(self) -> list[dict[str, Any]]:
        return [{"agency": "A"}, {"agency": "B"}, {"agency": "C"}]


class FakeResult:
    def keys(self) -> list[str]:
        return ["agency"]

    def mappings(self) -> FakeMappings:
        return FakeMappings()


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.statement = ""
        self.transaction = FakeTransaction()

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return self.transaction

    def exec_driver_sql(self, statement: str) -> None:
        self.commands.append(statement)

    def execute(self, statement: Any, _params: dict[str, Any]) -> FakeResult:
        self.statement = str(statement)
        return FakeResult()


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def connect(self) -> FakeConnection:
        return self.connection


def test_sql_execution_is_read_only_timed_and_row_limited():
    engine = FakeEngine()
    tool = SafeSQLTool(cast(Any, engine), max_rows=2, timeout_ms=900)
    result = tool.execute("SELECT agency FROM analytics_marts.dim_agencies")

    assert engine.connection.commands == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 900",
    ]
    assert "LIMIT 3" in engine.connection.statement
    assert engine.connection.transaction.rolled_back is True
    assert result.row_count == 2
    assert result.truncated is True
