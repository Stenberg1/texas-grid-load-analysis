"""Shared Plotly styling and save helper for all project charts."""
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "charts"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8984"
GRID = "#e8e7e3"
# Categorical slots, fixed order (validated: adjacent CVD dE >= 9.1)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

# Fixed fuel -> color mapping so a fuel keeps its color in every chart
FUEL_COLORS = {
    "Gas": SERIES[0],
    "Coal": SERIES[1],
    "Nuclear": SERIES[2],
    "Solar": SERIES[3],
    "Other": SERIES[4],
    "Wind": SERIES[5],
}

pio.templates["grid"] = go.layout.Template(
    layout=dict(
        font=dict(family="Inter, Helvetica, Arial, sans-serif", size=14, color=INK_2),
        title=dict(font=dict(size=20, color=INK), x=0.0, xref="paper", xanchor="left", y=0.95),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=SERIES,
        xaxis=dict(showgrid=False, zeroline=False, linecolor=GRID, ticks="outside", tickcolor=GRID,
                   title=dict(font=dict(color=INK_2))),
        yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=GRID,
                   title=dict(font=dict(color=INK_2))),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor="white", font=dict(color=INK)),
        margin=dict(l=80, r=40, t=110, b=110),
    )
)
pio.templates.default = "grid"


CAPTION_Y = -0.2


def add_caption(fig, text):
    """One-line takeaway under the plot."""
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0, y=CAPTION_Y,
                       xanchor="left", yanchor="top", showarrow=False,
                       font=dict(size=13, color=INK_2))


def save(fig, name, width=1100, height=620):
    CHARTS.mkdir(exist_ok=True)
    fig.write_image(CHARTS / f"{name}.png", width=width, height=height, scale=2)
    # the interactive version is embedded under a page caption, where the in-chart caption collides with the axis title
    fig.layout.annotations = [a for a in fig.layout.annotations if a.y != CAPTION_Y]
    fig.update_layout(margin_b=70)
    fig.write_html(CHARTS / f"{name}.html", include_plotlyjs="cdn")
