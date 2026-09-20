"""
Streamlit chatbot over a banker/branch database.

Ask a question in plain English -> a LangChain agent running on a local
Qwen model calls MCP tools to discover the schema and run SQL -> the app
renders the answer, the generated SQL, the result table and a chart.

Run:
    streamlit run app.py
"""
import subprocess
import sys
from pathlib import Path

import streamlit as st

from agent.charts import build_chart, er_diagram_figure
from agent.langchain_agent import BankAnalyticsAgent
from agent.qwen_client import QwenClient
from agent.theme import register_template

ROOT = Path(__file__).parent
DB_PATH = ROOT / "db" / "bank.db"

st.set_page_config(page_title="Banker & Branch Analytics", page_icon="🏦", layout="wide")
register_template()

SAMPLE_QUESTIONS = [
    "Which 5 branches have the highest total deposits?",
    "Show average customer satisfaction score by role.",
    "Which region has the most bankers rated Needs Improvement?",
    "Compare monthly sales target vs actual for bankers in the West region.",
    "How many bankers work at each branch?",
    "What is the average years of experience by branch type?",
]

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("⚙️ Settings")
    model = st.text_input("Ollama model", value="qwen3:8b")
    host = st.text_input("Ollama host", value="http://localhost:11434")

    client = QwenClient(model=model, host=host)
    ok, msg = client.is_available()
    if ok:
        st.success(f"Connected to '{model}'")
    else:
        st.error(msg)

    st.divider()
    st.subheader("Database")
    if DB_PATH.exists():
        st.caption(f"`{DB_PATH.name}` ready")
    else:
        st.warning("No database found yet.")
    if st.button("🔄 (Re)generate sample data"):
        with st.spinner("Generating synthetic banker & branch data..."):
            subprocess.run([sys.executable, str(ROOT / "db" / "generate_data.py")], check=True)
        st.success("Done — sample data regenerated.")
        st.rerun()

    st.divider()
    st.caption(
        "**Architecture:** Streamlit → LangChain agent → MCP server "
        "(`get_schema`, `run_sql_query`) → read-only SQLite."
    )
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ------------------------------------------------------------------ main --
st.title("🏦 Banker & Branch Analytics")
st.caption(
    "Ask in plain English — a LangChain agent on local Qwen discovers the schema "
    "over MCP, writes its own SQL, runs it read-only, and charts the result."
)

with st.expander("📐 Database schema (ER diagram)"):
    st.plotly_chart(er_diagram_figure(), width="stretch")

if not DB_PATH.exists():
    st.warning("No database yet — click **(Re)generate sample data** in the sidebar to create one.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

st.write("**Try asking:**")
cols = st.columns(3)
for i, q in enumerate(SAMPLE_QUESTIONS):
    if cols[i % 3].button(q, key=f"sample_{i}", width="stretch"):
        st.session_state.pending_question = q


def render_assistant(msg: dict, key_prefix: str) -> None:
    """Renders one assistant turn: answer, SQL, chart, table."""
    if msg.get("error"):
        st.error(msg["error"])
        if msg.get("sql"):
            with st.expander("Generated SQL"):
                st.code(msg["sql"], language="sql")
        return

    st.write(msg["answer"])
    with st.expander("🔍 Generated SQL & agent steps"):
        if msg.get("steps"):
            st.caption("MCP tool calls: " + " → ".join(msg["steps"]))
        st.code(msg["sql"], language="sql")

    df = msg.get("df")
    if df is not None and not df.empty:
        fig = build_chart(msg.get("chart_spec", {}), df)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_chart")
        st.dataframe(df, width="stretch", hide_index=True)


# ---- chat history ----
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message("user"):
        st.write(msg["question"])
    with st.chat_message("assistant"):
        render_assistant(msg, key_prefix=f"hist_{i}")

# ---- new input ----
question = st.chat_input("Ask about bankers or branches...")
if "pending_question" in st.session_state:
    question = st.session_state.pop("pending_question")

if question:
    with st.chat_message("user"):
        st.write(question)

    ok, msg = client.is_available()
    if not ok:
        with st.chat_message("assistant"):
            st.error(msg)
        st.session_state.messages.append({"question": question, "error": msg})
    else:
        agent = BankAnalyticsAgent(model=model, host=host)
        history = [
            {"question": m["question"], "sql": m.get("sql", "")}
            for m in st.session_state.messages
            if not m.get("error")
        ]
        with st.chat_message("assistant"):
            with st.spinner(
                "Agent is discovering the schema over MCP, writing SQL, and analyzing "
                "the result... (a local 8B model can take a minute)"
            ):
                result = agent.ask(question, history)

            record = {
                "question": question,
                "sql": result.sql,
                "answer": result.answer,
                "chart_spec": result.chart_spec,
                "df": result.df,
                "steps": result.steps,
                "error": result.error,
            }
            render_assistant(record, key_prefix="live")

        st.session_state.messages.append(record)
