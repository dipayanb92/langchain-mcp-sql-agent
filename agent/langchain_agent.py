"""
The LangChain agent.

It owns no database code at all. Everything it knows about the bank comes
from tools served by the MCP server (mcp_server/bank_server.py), which it
launches over stdio via langchain-mcp-adapters:

    get_schema      -> the agent discovers the tables/columns at runtime
    run_sql_query   -> the agent submits SQL and gets rows back

Flow for one question:
    1. create_agent() runs a tool-calling loop: get_schema -> run_sql_query
       -> final natural-language answer.
    2. We pull the SQL and the result rows out of the *tool-call trail*
       rather than from the model's prose, so the table and chart are
       always the real query output (no LLM-retyped numbers).
    3. A short follow-up call picks a chart, with a deterministic
       heuristic as fallback if the model's pick is unusable.
"""
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama

ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER_MODULE = "mcp_server.bank_server"

SYSTEM_PROMPT_TEMPLATE = """You are a senior banking data analyst. You answer questions \
about a bank's bankers and branches by querying a read-only SQLite database.

This is the live schema, fetched from the MCP server:

{schema}

You have one tool you must use:
- run_sql_query: runs ONE read-only SQLite SELECT and returns the rows.
  (get_schema is also available if you need to re-check the schema.)

Rules:
- Write ONE SQLite SELECT statement and call run_sql_query with it, exactly once.
- CHOOSE COLUMNS LITERALLY. Map the user's words to the column whose name actually
  matches. "deposits" means branches.total_deposits. "loans" means branches.total_loans.
  "sales" means bankers.monthly_sales_actual. "target" means bankers.monthly_sales_target.
  Never substitute a different measure than the one asked for, and never SUM a column
  that is already a per-row total unless the question asks you to group rows together.
- Join bankers to branches with bankers.branch_id = branches.branch_id ONLY when the
  question genuinely needs columns from both tables. If every column you need is in one
  table, query that table alone.
- Do NOT put semicolons inside the query.
- Only SELECT. Never INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/PRAGMA/ATTACH.
- If run_sql_query returns an "error" field, read the error, fix the SQL, and try once more.
- As soon as you have rows back, STOP calling tools and write your final answer: 2-4
  plain-English sentences citing concrete numbers from those rows. Describe the numbers
  using the same measure name the column actually represents.
"""

CHART_SYSTEM_PROMPT = """You choose the best chart for a SQL result set.

Reply with ONLY a JSON object, no prose:
{"type": "bar"|"line"|"pie"|"scatter"|"none", "x": <column or null>, \
"y": <column or null>, "color": <column or null>, "title": <short title or null>}

Guidance:
- "bar": compare one measure across categories (the usual choice).
- "line": only when a genuine time or ordered sequence column exists.
- "pie": only for 6 or fewer categories that sum to a meaningful whole.
- "scatter": compare two numeric measures per row.
- "none": a single value, a single row, or nothing sensibly plottable.
- x/y/color must be EXACT column names from the result, or null.
"""


@dataclass
class AgentResult:
    question: str
    sql: str = ""
    df: pd.DataFrame | None = None
    answer: str = ""
    chart_spec: dict = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    error: str | None = None


def _tool_text(message: ToolMessage) -> str:
    """MCP results arrive as LangChain content blocks; flatten to text."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def _tool_payload(message: ToolMessage) -> dict:
    try:
        payload = json.loads(_tool_text(message))
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def heuristic_chart(df: pd.DataFrame | None) -> dict:
    """Deterministic fallback so a chart still appears if the model's pick is unusable."""
    if df is None or df.empty or len(df) < 2:
        return {"type": "none"}
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical = [c for c in df.columns if c not in numeric]
    if not (numeric and categorical):
        return {"type": "none"}
    x = categorical[0]
    y = next((c for c in numeric if not c.lower().endswith("_id")), numeric[0])
    if df[x].nunique() > 30:
        return {"type": "none"}
    return {"type": "bar", "x": x, "y": y, "color": None, "title": f"{y} by {x}"}


class BankAnalyticsAgent:
    def __init__(
        self,
        model: str = "qwen3:8b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_steps: int = 12,
    ):
        self.model = model
        self.host = host
        self.temperature = temperature
        self.max_steps = max_steps

    # ---------------------------------------------------------------- setup --
    def _llm(self) -> ChatOllama:
        # reasoning=False maps to Ollama's "think" flag: Qwen3 is a hybrid
        # reasoning model and we want tool calls + clean prose, not a trace.
        return ChatOllama(
            model=self.model,
            base_url=self.host,
            temperature=self.temperature,
            reasoning=False,
        )

    def _mcp_connection(self) -> dict:
        return {
            "bank": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", MCP_SERVER_MODULE],
                "cwd": str(ROOT),
            }
        }

    # ------------------------------------------------------------ chart step --
    async def _pick_chart(self, question: str, df: pd.DataFrame) -> dict:
        fallback = heuristic_chart(df)
        if df is None or df.empty or len(df) < 2:
            return {"type": "none"}
        try:
            llm = self._llm().bind(format="json")
            prompt = (
                f"Question: {question}\n"
                f"Columns: {list(df.columns)}\n"
                f"Rows ({len(df)} total, first 15 shown):\n"
                f"{df.head(15).to_json(orient='records')}"
            )
            reply = await llm.ainvoke(
                [("system", CHART_SYSTEM_PROMPT), ("human", prompt)]
            )
            spec = json.loads(reply.content if isinstance(reply.content, str) else _flatten(reply.content))
            if not isinstance(spec, dict) or "type" not in spec:
                return fallback
            # columns must actually exist, else fall back
            for key in ("x", "y", "color"):
                col = spec.get(key)
                if col and col not in df.columns:
                    return fallback
            return spec
        except Exception:  # noqa: BLE001 - a chart is never worth failing the answer over
            return fallback

    # -------------------------------------------------------------- main run --
    async def _ask_async(self, question: str, history: list[dict]) -> AgentResult:
        result = AgentResult(question=question)

        preamble = ""
        if history:
            prior = "\n".join(
                f"Q: {h['question']}\nSQL used: {h.get('sql', '')}" for h in history[-3:]
            )
            preamble = f"Earlier in this conversation:\n{prior}\n\n"

        try:
            client = MultiServerMCPClient(self._mcp_connection())
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001
            result.error = f"Couldn't start the MCP server or load its tools: {exc}"
            return result

        # Fetch the schema from MCP once, up front, and put it in the system
        # prompt. Nothing about the schema is hardcoded here - it still comes
        # from the server - but the model plans far more accurately with the
        # columns in front of it than with them buried in a tool result, and
        # it saves a whole model turn.
        try:
            schema_tool = next(t for t in tools if t.name == "get_schema")
            schema = _flatten(await schema_tool.ainvoke({}))
            result.steps.append("mcp: get_schema (prefetched)")
        except Exception as exc:  # noqa: BLE001
            result.error = f"Couldn't fetch the schema from the MCP server: {exc}"
            return result

        agent = create_agent(
            model=self._llm(),
            tools=tools,
            system_prompt=SYSTEM_PROMPT_TEMPLATE.format(schema=schema),
        )

        try:
            state = await agent.ainvoke(
                {"messages": [HumanMessage(content=f"{preamble}{question}")]},
                config={"recursion_limit": self.max_steps},
            )
        except Exception as exc:  # noqa: BLE001
            result.error = f"The agent failed to complete: {exc}"
            return result

        # --- read the tool-call trail: SQL + rows are ground truth from here ---
        sql_by_call_id: dict[str, str] = {}
        last_error = None
        for message in state["messages"]:
            if isinstance(message, AIMessage):
                for call in message.tool_calls or []:
                    result.steps.append(f"tool: {call['name']}")
                    if call["name"] == "run_sql_query":
                        sql_by_call_id[call["id"]] = call["args"].get("sql", "")
            elif isinstance(message, ToolMessage) and message.name == "run_sql_query":
                payload = _tool_payload(message)
                if payload.get("error"):
                    last_error = payload["error"]
                    continue
                result.sql = sql_by_call_id.get(message.tool_call_id, result.sql)
                result.df = pd.DataFrame(payload.get("rows", []))
                last_error = None

        final = next(
            (
                m
                for m in reversed(state["messages"])
                if isinstance(m, AIMessage) and not m.tool_calls and str(m.content).strip()
            ),
            None,
        )
        result.answer = str(final.content).strip() if final else ""

        if result.df is None:
            result.error = last_error or (
                "The agent never produced a successful query. Try rephrasing the question."
            )
            return result

        result.chart_spec = await self._pick_chart(question, result.df)
        if not result.answer:
            result.answer = f"Returned {len(result.df)} row(s)."
        return result

    def ask(self, question: str, history: list[dict] | None = None) -> AgentResult:
        """Synchronous entry point (Streamlit calls this)."""
        return asyncio.run(self._ask_async(question, history or []))


def _flatten(content) -> str:
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)
