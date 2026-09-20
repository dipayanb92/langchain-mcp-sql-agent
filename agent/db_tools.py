"""
Schema description + SQL safety validation + read-only execution.
Shared by the MCP server (mcp_server/bank_server.py) so the *only* place
that ever touches the database is a validated, read-only tool call.
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "truncate", "attach", "detach", "pragma", "vacuum", "reindex", "grant",
    "revoke", "into",  # blocks SELECT ... INTO outfile-style tricks
]

SCHEMA_DESCRIPTION = """\
Table: branches
  branch_id       INTEGER  PRIMARY KEY
  branch_name     TEXT
  city            TEXT
  state           TEXT
  region          TEXT     -- one of: Northeast, Southeast, Midwest, Southwest, West
  branch_type     TEXT     -- one of: Metro, Urban, Suburban, Rural
  opened_date     TEXT     -- ISO date
  manager_name    TEXT
  total_deposits  REAL     -- USD
  total_loans     REAL     -- USD
  customer_count  INTEGER

Table: bankers
  banker_id                   INTEGER  PRIMARY KEY
  first_name                  TEXT
  last_name                   TEXT
  email                       TEXT
  role                        TEXT     -- one of: Relationship Manager, Branch Manager,
                                        --   Loan Officer, Financial Advisor, Teller, Credit Analyst
  branch_id                   INTEGER  REFERENCES branches(branch_id)
  hire_date                   TEXT     -- ISO date
  years_experience            INTEGER
  monthly_sales_target        REAL     -- USD
  monthly_sales_actual        REAL     -- USD
  customer_satisfaction_score REAL     -- 1.0 - 5.0
  performance_rating          TEXT     -- one of: Excellent, Good, Average, Needs Improvement

Relationship: bankers.branch_id -> branches.branch_id (many bankers per branch)
"""


def sanitize_and_validate_sql(sql: str) -> str:
    """Strips a harmless single trailing semicolon, then enforces: exactly one
    SELECT/WITH statement, no embedded semicolons, no write/DDL keywords.
    Returns the cleaned SQL (safe to execute) or raises ValueError."""
    if not sql or not sql.strip():
        raise ValueError("No SQL provided.")
    cleaned = sql.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if ";" in cleaned:
        raise ValueError(
            "Only a single statement is allowed. Remove any semicolons except "
            "one optional trailing semicolon at the very end."
        )
    stripped = cleaned.lower()
    if not (stripped.startswith("select") or stripped.startswith("with")):
        raise ValueError("Only SELECT statements are allowed.")
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", stripped):
            raise ValueError(f"Query contains a disallowed keyword: '{kw}'.")
    return cleaned


def validate_sql(sql: str) -> None:
    """Back-compat wrapper: raises ValueError on an unsafe query, discards the
    cleaned string. Prefer sanitize_and_validate_sql() for new code."""
    sanitize_and_validate_sql(sql)


def run_query(db_path: Path, sql: str) -> pd.DataFrame:
    """Executes sql against db_path over a read-only connection. Caller must
    have already run validate_sql() on it."""
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()
