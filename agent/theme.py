"""
Shared color palette + Plotly template so every chart the agent draws
looks consistent. Categorical hues are used in a FIXED order (never
cycled/reassigned) and the sequential ramp is used for pure-magnitude
encodings (single continuous measure, e.g. a heatmap or a ranked bar
where color reinforces the value itself).
"""
import plotly.graph_objects as go
import plotly.io as pio

# Fixed-order categorical palette (blue, orange, aqua, yellow, magenta, green, violet, red)
CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

# Sequential single-hue ramp (blue), light -> dark, for magnitude encodings
SEQUENTIAL_BLUE = [
    "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
    "#256abf", "#184f95", "#0d366b",
]

# Diverging pair: blue (low) <-> gray midpoint <-> red (high)
DIVERGING = [[0, "#256abf"], [0.5, "#f0efec"], [1, "#e34948"]]

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

TEMPLATE_NAME = "bank_agent"


def register_template():
    template = go.layout.Template()
    template.layout = go.Layout(
        colorway=CATEGORICAL,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=INK_SECONDARY, size=13),
        title=dict(font=dict(color=INK_PRIMARY, size=16)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        xaxis=dict(
            gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor="#c3c2b7",
            tickfont=dict(color=INK_MUTED), title=dict(font=dict(color=INK_SECONDARY)),
        ),
        yaxis=dict(
            gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, linecolor="#c3c2b7",
            tickfont=dict(color=INK_MUTED), title=dict(font=dict(color=INK_SECONDARY)),
        ),
        legend=dict(font=dict(color=INK_SECONDARY)),
        margin=dict(l=60, r=30, t=60, b=50),
    )
    pio.templates[TEMPLATE_NAME] = template
    pio.templates.default = TEMPLATE_NAME
