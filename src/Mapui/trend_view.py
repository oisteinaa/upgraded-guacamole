#!/usr/bin/env python

import sys
import os
import requests
import numpy as np
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from config import cache

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_mastliste

IPADDR_RESTSERVER = 'http://10.147.20.10:5000'


def main(app):
    geom = get_mastliste()

    app.layout = html.Div([
        html.H1("RMS Baseline Trend"),
        dcc.RadioItems(
            id='baseline-window',
            options=[
                {'label': '1 week baseline', 'value': '1_weeks'},
                {'label': '2 week baseline', 'value': '2_weeks'},
                {'label': '4 week baseline', 'value': '4_weeks'},
            ],
            value='1_weeks',
            inline=True,
            style={'margin': '10px 0'},
        ),
        dcc.Graph(id='trend-map', style={'height': '70vh'}),
        dcc.Graph(id='trend-line', style={'height': '40vh'}),
        dcc.Interval(
            id='trend-interval',
            interval=60 * 1000,  # in milliseconds
            n_intervals=0
        ),
    ], style={'padding': '10px 20px'})

    @cache.memoize()
    def get_current_rms():
        r = requests.get(f'{IPADDR_RESTSERVER}/rms')
        return r.json()

    @cache.memoize()
    def get_baseline():
        r = requests.get(f'{IPADDR_RESTSERVER}/rms_baseline')
        return r.json()

    @app.callback(
        Output('trend-map', 'figure'),
        Output('trend-line', 'figure'),
        Input('trend-interval', 'n_intervals'),
        Input('baseline-window', 'value'),
    )
    def update_trend(_, window):
        current = get_current_rms()
        baseline = get_baseline()

        rms = current.get('rms', [])
        base = baseline.get(window)

        if not rms or not base:
            return go.Figure(), go.Figure()

        n = min(len(rms), len(base), geom.shape[0])
        df = geom.iloc[:n].copy()
        df['current_rms'] = rms[:n]
        df['baseline_rms'] = [b if b is not None else np.nan for b in base[:n]]
        df['deviation_pct'] = (
            (df['current_rms'] - df['baseline_rms']) / df['baseline_rms'].replace(0, np.nan) * 100
        )

        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df['longitude'], df['latitude']), crs="EPSG:4326"
        )
        map_fig = px.scatter_map(
            gdf,
            lat=gdf.geometry.y,
            lon=gdf.geometry.x,
            color='deviation_pct',
            color_continuous_scale='RdBu_r',
            range_color=[-50, 50],
            zoom=11,
            map_style='open-street-map',
            hover_data={'channel': True, 'current_rms': True, 'baseline_rms': True, 'deviation_pct': ':.1f'},
        )
        map_fig.update_layout(
            title=f'Current RMS deviation from {window.replace("_", " ")} baseline',
            uirevision='trend-map',
        )

        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(y=df['baseline_rms'], mode='lines', name='Baseline'))
        line_fig.add_trace(go.Scatter(y=df['current_rms'], mode='lines', name='Current'))
        line_fig.update_layout(
            title='Current RMS vs baseline (per channel)',
            xaxis_title='Channel index',
            yaxis_title='RMS',
            uirevision='trend-line',
        )

        return map_fig, line_fig

    return app


if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    app.run(debug=True)
