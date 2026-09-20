"""
MCP server exposing the banker/branch SQLite database as two tools:
  - get_schema      : the table/column reference the agent reasons over
  - run_sql_query    : validated, read-only SQL execution

This is the ONLY code in the whole project that touches the database.
The LangChain agent (agent/langchain_agent.py) never opens bank.db
directly — it only ever calls these tools over MCP, exactly like it
would call a tool exposed by someone else's MCP server.

Run standalone for debugging:
    python -m mcp_server.bank_server
(normally it's launched automatically, over stdio, by the LangChain
agent via langchain-mcp-adapters)
"""
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from agent.db_tools import SCHEMA_DESCRIPTION, run_query, sanitize_and_validate_sql

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "bank.db"

mcp = FastMCP(
    "bank-analytics",
    instructions=(
        "Tools for analyzing a bank's bankers and branches. Always call "
        "get_schema before writing SQL, then run_sql_query with a single "
        "read-only SELECT statement."
    ),
)


@mcp.tool()
def get_schema() -> str:
    """Return the table/column schema and relationships of the banker/branch database."""
    return SCHEMA_DESCRIPTION


@mcp.tool()
def run_sql_query(sql: str) -> dict:
    """Run one read-only SQLite query against the banker/branch database and return the rows.

    Args:
        sql: A single SQLite SELECT statement (a WITH...SELECT CTE is fine).
            No semicolons. No INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/PRAGMA/
            ATTACH — the query is rejected if it contains any of those.
            Join bankers to branches via bankers.branch_id = branches.branch_id.
    """
    try:
        clean_sql = sanitize_and_validate_sql(sql)
    except ValueError as exc:
        return {"error": str(exc)}

    if not DB_PATH.exists():
        return {"error": f"Database not found at {DB_PATH}. Run db/generate_data.py first."}

    try:
        df = run_query(DB_PATH, clean_sql)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"SQL failed to execute: {exc}"}

    return {
        "columns": list(df.columns),
        "row_count": len(df),
        "rows": json.loads(df.to_json(orient="records")),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
