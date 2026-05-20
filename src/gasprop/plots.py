from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def make_line_chart(frame: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame[x], y=frame[y], mode="lines+markers", name=y))
    fig.update_layout(title=title, xaxis_title=x, yaxis_title=y, template="plotly_dark", height=420)
    return fig


def make_surface_chart(frame: pd.DataFrame, x: str, y: str, z: str, title: str) -> go.Figure:
    pivot = frame.pivot(index=y, columns=x, values=z)
    fig = go.Figure(data=[go.Surface(x=pivot.columns, y=pivot.index, z=pivot.values)])
    fig.update_layout(title=title, template="plotly_dark", height=640, scene=dict(xaxis_title=x, yaxis_title=y, zaxis_title=z))
    return fig


def make_scatter(frame: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame[x], y=frame[y], mode="lines", name=y))
    fig.update_layout(title=title, xaxis_title=x, yaxis_title=y, template="plotly_dark", height=420)
    return fig


def make_histogram(values, title: str, xaxis_title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=values, nbinsx=30))
    fig.update_layout(title=title, xaxis_title=xaxis_title, yaxis_title="Count", template="plotly_dark", height=420)
    return fig

