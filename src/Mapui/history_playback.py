#!/usr/bin/env python

import sys
import os
import requests
import datetime
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_mastliste

IPADDR_RESTSERVER = 'http://10.147.20.10:5000'


def main(app):
    geom = get_mastliste()

    app.layout = html.Div([
        html.H1("Historical RMS Playback"),
        html.Div([
            dcc.DatePickerSingle(
                id='history-date',
                date=(datetime.date.today() - datetime.timedelta(days=1)).isoformat(),
            ),
            html.Button('Load day', id='history-load', n_clicks=0, style={'margin-left': '10px'}),
        ]),
        html.Div(id='history-status', style={'margin': '10px 0'}),
        dcc.Slider(id='history-slider', min=0, max=0, step=1, value=0),
        html.Div(id='history-frame-time', style={'margin': '10px 0', 'font-weight': 'bold'}),
        dcc.Graph(id='history-map', style={'height': '70vh', 'margin-top': '10px'}),
        dcc.Store(id='history-data'),
    ], style={'padding': '10px 20px'})

    @app.callback(
        Output('history-data', 'data'),
        Output('history-status', 'children'),
        Output('history-slider', 'max'),
        Output('history-slider', 'value'),
        Input('history-load', 'n_clicks'),
        State('history-date', 'date'),
    )
    def load_day(n_clicks, date_value):
        if not n_clicks or not date_value:
            return None, "Pick a date and click Load day.", 0, 0

        date_str = date_value.replace('-', '')
        r = requests.get(f'{IPADDR_RESTSERVER}/rms_history/{date_str}')
        if r.status_code != 200:
            return None, f"No data found for {date_value}.", 0, 0

        frames = r.json()
        if not frames:
            return None, f"No captures recorded for {date_value}.", 0, 0

        # Sort chronologically by real capture time where available; frames
        # without a timestamp (older files predating this feature) keep
        # their original filename-sorted order, trailing the timed ones.
        frames.sort(key=lambda fr: (fr.get('time') is None, fr.get('time') or 0))

        return frames, f"Loaded {len(frames)} captures for {date_value}.", max(len(frames) - 1, 0), 0

    @app.callback(
        Output('history-map', 'figure'),
        Output('history-frame-time', 'children'),
        Input('history-slider', 'value'),
        State('history-data', 'data'),
    )
    def update_history_map(frame_index, frames):
        if not frames:
            return go.Figure(), ""

        frame_index = min(frame_index, len(frames) - 1)
        frame = frames[frame_index]
        rms = frame.get('rms', [])
        capture_time = frame.get('time')

        if capture_time is not None:
            label = datetime.datetime.fromtimestamp(capture_time).strftime('%Y-%m-%d %H:%M:%S')
        else:
            label = f'capture {frame_index + 1} of {len(frames)} (no timestamp recorded for this capture)'

        n = min(len(rms), geom.shape[0])
        df = geom.iloc[:n].copy()
        df['rms'] = rms[:n]

        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df['longitude'], df['latitude']), crs="EPSG:4326"
        )
        fig = px.scatter_map(
            gdf,
            lat=gdf.geometry.y,
            lon=gdf.geometry.x,
            color='rms',
            range_color=[0, 10000],
            zoom=11,
            map_style='open-street-map',
            hover_data={'channel': True, 'rms': True, 'distance': True},
        )
        fig.update_layout(
            title=f'Capture {frame_index + 1} of {len(frames)} — {label}',
            uirevision='history-map',
        )
        return fig, f'Showing: {label}'

    return app


if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    app.run(debug=True)
