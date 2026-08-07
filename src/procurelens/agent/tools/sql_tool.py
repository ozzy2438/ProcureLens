"""Read-only SQL access to explicitly allowlisted dbt marts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import Engine, create_engine, text

from procurelens.config import get_settings

ALLOWED_SCHEMAS = ("analytics_marts",)
ALLOWED_TABLES = ("fct_contracts", "dim_agencies")
MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 5_000

_DENIED_FUNCTIONS = {
    "current_setting",
    "dblink",
    "dblink_connect",
    "lo_export",
    "lo_import",
    "pg_ls_dir",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_stat_file",
}


class UnsafeQueryError(ValueError):
    """Raised before execution when SQL violates the read-only policy."""


@dataclass(frozen=True)
class SQLResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    query: str

    def model_dump(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "query": self.query,
        }


@dataclass(frozen=True)
class SQLQueryPlan:
    """Reviewed SQL template selected for a supported procurement intent."""

    intent: str
    query: str
    params: dict[str, Any]


def _serialise(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def validate_select_query(
    query: str,
    *,
    allowed_schemas: tuple[str, ...] = ALLOWED_SCHEMAS,
    allowed_tables: tuple[str, ...] = ALLOWED_TABLES,
) -> str:
    """Parse and validate one PostgreSQL query before database execution."""
    import sqlglot
    from sqlglot import exp

    if not query.strip():
        raise UnsafeQueryError("SQL query cannot be empty")
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQueryError("SQL query could not be parsed") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("exactly one SQL statement is allowed")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeQueryError("only SELECT queries are allowed")

    denied_nodes = (
        exp.Alter,
        exp.Command,
        exp.Copy,
        exp.Create,
        exp.Delete,
        exp.Drop,
        exp.Insert,
        exp.Into,
        exp.Merge,
        exp.Transaction,
        exp.Update,
    )
    if any(statement.find(node_type) is not None for node_type in denied_nodes):
        raise UnsafeQueryError("query contains a prohibited operation")

    allowed_schema_set = {schema.lower() for schema in allowed_schemas}
    allowed_table_set = {table.lower() for table in allowed_tables}
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in cte_names:
            continue
        schema_name = table.db.lower() if table.db else ""
        if schema_name not in allowed_schema_set:
            raise UnsafeQueryError(
                f"table {table.sql()} is outside the allowed dbt mart schemas"
            )
        if table_name not in allowed_table_set:
            raise UnsafeQueryError(f"table {table_name} is not allowlisted")

    for function in statement.find_all(exp.Func):
        function_name = (
            function.name.lower()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().lower()
        )
        if function_name in _DENIED_FUNCTIONS:
            raise UnsafeQueryError(f"function {function_name} is prohibited")
    # Preserve SQLAlchemy ``:named`` bind markers; sqlglot renders them as
    # psycopg-style placeholders which SQLAlchemy would escape a second time.
    return query.strip().removesuffix(";").strip()


class SafeSQLTool:
    """Execute validated SELECTs in a read-only transaction with hard limits."""

    def __init__(
        self,
        engine: Engine,
        *,
        allowed_schemas: tuple[str, ...] = ALLOWED_SCHEMAS,
        allowed_tables: tuple[str, ...] = ALLOWED_TABLES,
        max_rows: int = MAX_ROWS,
        timeout_ms: int = STATEMENT_TIMEOUT_MS,
    ) -> None:
        if not 1 <= max_rows <= 5_000:
            raise ValueError("max_rows must be between 1 and 5000")
        if not 100 <= timeout_ms <= 60_000:
            raise ValueError("timeout_ms must be between 100 and 60000")
        self.engine = engine
        self.allowed_schemas = allowed_schemas
        self.allowed_tables = allowed_tables
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms

    def execute(self, query: str, params: Mapping[str, Any] | None = None) -> SQLResult:
        safe_query = validate_select_query(
            query,
            allowed_schemas=self.allowed_schemas,
            allowed_tables=self.allowed_tables,
        )
        bounded_query = (
            f"SELECT * FROM ({safe_query}) AS procurelens_safe_query LIMIT {self.max_rows + 1}"
        )
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql(f"SET LOCAL statement_timeout = {self.timeout_ms}")
                result = connection.execute(text(bounded_query), dict(params or {}))
                columns = list(result.keys())
                raw_rows = result.mappings().all()
            finally:
                transaction.rollback()
        truncated = len(raw_rows) > self.max_rows
        rows = [
            {key: _serialise(value) for key, value in dict(row).items()}
            for row in raw_rows[: self.max_rows]
        ]
        return SQLResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            query=safe_query,
        )

    def answer_question(
        self,
        question: str,
        context: Mapping[str, Any] | None = None,
    ) -> SQLResult:
        """Map supported procurement intents to reviewed, parameterised SQL templates."""
        plan = plan_nl_query(question, context)
        return self.execute(plan.query, plan.params)

    def close(self) -> None:
        self.engine.dispose()


def plan_nl_query(
    question: str,
    context: Mapping[str, Any] | None = None,
) -> SQLQueryPlan:
    """Return the exact allowlisted query plan without touching the database."""
    import re

    lowered = question.lower()
    context = context or {}
    agency = str(context.get("agency", "")).strip()
    params: dict[str, Any] = {"agency_pattern": f"%{agency}%" if agency else "%"}

    requested_limit = context.get("limit")
    if requested_limit is None:
        match = re.search(r"\b(?:top|first)\s+(\d{1,3})\b", lowered)
        requested_limit = int(match.group(1)) if match else None
    if requested_limit is not None:
        requested_limit = max(1, min(int(requested_limit), 50))

    if any(term in lowered for term in ("supplier", "incumbent", "vendor")):
        intent = "suppliers"
        query = """
            SELECT supplier_name,
                   COUNT(*) AS contract_count,
                   SUM(award_value_aud) AS total_value_aud
            FROM analytics_marts.fct_contracts
            WHERE agency ILIKE :agency_pattern AND supplier_name IS NOT NULL
            GROUP BY supplier_name
            ORDER BY total_value_aud DESC
        """
        if requested_limit is not None:
            query += " LIMIT :requested_limit"
            params["requested_limit"] = requested_limit
    elif any(term in lowered for term in ("amend", "variation", "uplift")):
        intent = "amendments"
        query = """
            SELECT agency,
                   COUNT(*) AS contract_count,
                   AVG(CASE WHEN was_amended_up THEN 1.0 ELSE 0.0 END) AS amendment_rate,
                   SUM(value_uplift_aud) AS total_uplift_aud
            FROM analytics_marts.fct_contracts
            WHERE agency ILIKE :agency_pattern
            GROUP BY agency
            ORDER BY amendment_rate DESC
        """
    else:
        intent = "spend"
        query = """
            SELECT agency, contracts_all_time, total_spend_aud,
                   avg_contract_aud, last_award_date
            FROM analytics_marts.dim_agencies
            WHERE agency ILIKE :agency_pattern
            ORDER BY total_spend_aud DESC
        """
    query = query.strip()
    validate_select_query(query)
    return SQLQueryPlan(intent=intent, query=query, params=params)


def build_sql_tool(database_url: str | None = None) -> SafeSQLTool:
    settings = get_settings()
    schemas = tuple(
        schema.strip() for schema in settings.agent_sql_schemas.split(",") if schema.strip()
    )
    engine = create_engine(
        database_url or settings.agent_database_url or settings.database_url,
        pool_pre_ping=True,
    )
    return SafeSQLTool(
        engine,
        allowed_schemas=schemas,
        max_rows=settings.agent_sql_max_rows,
        timeout_ms=settings.agent_sql_timeout_ms,
    )


def run_nl_query(question: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Convenience facade used by the agent tool registry."""
    return build_sql_tool().answer_question(question, context).model_dump()
