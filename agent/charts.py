"""
Renders a Plotly figure from the chart spec Qwen returns (chart type +
column names) plus the query result DataFrame. Falls back gracefully
(returns None) when the spec doesn't fit the data, so the app can just
show the table instead.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .theme import CATEGORICAL, SEQUENTIAL_BLUE, TEMPLATE_NAME

MAX_CATEGORIES = 30  # beyond this a bar/pie chart stops being readable


def _valid_columns(spec: dict, df: pd.DataFrame) -> bool:
    for key in ("x", "y"):
        col = spec.get(key)
        if col and col not in df.columns:
            return False
    color = spec.get("color")
    if color and color not in df.columns:
        return False
    return True


def build_chart(spec: dict, df: pd.DataFrame):
    """Returns a Plotly Figure, or None if no sensible chart applies."""
    if not spec or df is None or df.empty:
        return None

    chart_type = (spec.get("type") or "none").lower()
    if chart_type == "none":
        return None
    if not _valid_columns(spec, df):
        return None

    x, y, color, title = spec.get("x"), spec.get("y"), spec.get("color"), spec.get("title")

    plot_df = df
    if x and chart_type in ("bar", "pie") and plot_df[x].nunique() > MAX_CATEGORIES:
        # keep the chart legible: show the top N by y (or by count)
        sort_col = y if y and y in plot_df.columns else x
        plot_df = plot_df.nlargest(MAX_CATEGORIES, sort_col) if y else plot_df.head(MAX_CATEGORIES)

    try:
        if chart_type == "bar":
            fig = px.bar(
                plot_df, x=x, y=y, color=color, title=title,
                color_discrete_sequence=CATEGORICAL,
                color_continuous_scale=SEQUENTIAL_BLUE if color and pd.api.types.is_numeric_dtype(plot_df.get(color, pd.Series(dtype=float))) else None,
            )
            fig.update_traces(marker_line_width=0)
        elif chart_type == "line":
            fig = px.line(plot_df, x=x, y=y, color=color, title=title, color_discrete_sequence=CATEGORICAL, markers=True)
            fig.update_traces(line_width=2)
        elif chart_type == "pie":
            fig = px.pie(plot_df, names=x, values=y, title=title, color_discrete_sequence=CATEGORICAL)
        elif chart_type == "scatter":
            fig = px.scatter(plot_df, x=x, y=y, color=color, title=title, color_discrete_sequence=CATEGORICAL)
            fig.update_traces(marker=dict(size=9))
        else:
            return None
    except Exception:
        return None

    fig.update_layout(template=TEMPLATE_NAME, legend_title_text=color or "")
    return fig


def er_diagram_figure():
    """A small static ER diagram of the two-table schema (no graphviz binary needed)."""
    fig = go.Figure()

    def table_box(x0, y0, x1, y1, title, cols, color):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                       line=dict(color=color, width=2), fillcolor="#fcfcfb")
        fig.add_shape(type="rect", x0=x0, y0=y1 - 0.35, x1=x1, y1=y1,
                       line=dict(color=color, width=2), fillcolor=color)
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 - 0.175, text=f"<b>{title}</b>",
                            showarrow=False, font=dict(color="white", size=13))
        for i, c in enumerate(cols):
            fig.add_annotation(x=x0 + 0.15, y=y1 - 0.6 - i * 0.3, text=c,
                                showarrow=False, xanchor="left",
                                font=dict(color="#0b0b0b", size=11))

    branch_cols = ["branch_id (PK)", "branch_name", "city / state / region",
                   "branch_type", "opened_date", "manager_name",
                   "total_deposits", "total_loans", "customer_count"]
    banker_cols = ["banker_id (PK)", "first_name / last_name", "email", "role",
                   "branch_id (FK)", "hire_date", "years_experience",
                   "monthly_sales_target", "monthly_sales_actual",
                   "customer_satisfaction_score", "performance_rating"]

    table_box(0, 2.6, 4.2, 6.3, "branches", branch_cols, CATEGORICAL[0])
    table_box(7.6, 0, 12.1, 4.4, "bankers", banker_cols, CATEGORICAL[1])

    # connector: branches (1) -> bankers (many)
    fig.add_annotation(x=7.6, y=2.6, ax=4.2, ay=4.4, xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=2, arrowwidth=2, arrowcolor="#898781",
                        text="")
    # Only the cardinality rides the connector - short enough that it can
    # never collide with a table box. The join expression goes in the
    # subtitle, where it has room to breathe.
    fig.add_annotation(
        x=5.9, y=3.5, text="1 : many",
        showarrow=False, font=dict(color="#52514e", size=11),
        bgcolor="#fcfcfb", bordercolor="#e1e0d9", borderwidth=1, borderpad=4,
    )

    fig.update_xaxes(visible=False, range=[-0.4, 12.5])
    fig.update_yaxes(visible=False, range=[-0.4, 6.8])
    fig.update_layout(
        template=TEMPLATE_NAME,
        title=dict(
            text="Database schema<br>"
                 "<span style='font-size:11px;color:#898781'>"
                 "one branch has many bankers &nbsp;·&nbsp; "
                 "bankers.branch_id = branches.branch_id</span>"
        ),
        height=440, margin=dict(l=10, r=10, t=70, b=10), showlegend=False,
    )
    return fig
