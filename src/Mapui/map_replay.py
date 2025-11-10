#!/usr/bin/env python3
from flask import app
import geopandas as gpd
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html
import dash
from dash.dependencies import Input, Output, State
import requests
import datetime
import sys, os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_mastliste

BASE_URL = "http://127.0.0.1:5000"


def main(app, date="20251110", frame_interval=10):
    geom = get_mastliste()

    app.layout = html.Div([
        html.Div([
            dcc.Graph(id="map-plot", style={'height': '90vh'}),
            html.Div(id="map-info", style={'margin-top': '10px', 'font-size': '18px'}),

            html.Div([
                html.Button("▶ Start Replay", id="start-btn", n_clicks=0, style={'margin-right': '10px'}),
                html.Button("⏸ Pause", id="pause-btn", n_clicks=0, style={'margin-right': '10px'}),
                html.Button("⏵ Resume", id="resume-btn", n_clicks=0)
            ], style={'margin-bottom': '10px'}),

            dcc.Store(id="rms-data", storage_type="memory"),
            dcc.Store(id="frame-index", storage_type="memory", data=0),
            dcc.Store(id="is-playing", storage_type="memory", data=False),
            dcc.Interval(
                id="play-interval",
                interval=frame_interval * 1000,  # milliseconds
                n_intervals=0,
                disabled=True
            ),
            dcc.RadioItems(
                id="view-selector",
                options=[
                    {'label': 'Open Street Map', 'value': 'open-street-map'},
                    {'label': 'Satellite', 'value': 'satellite'}
                ],
                value='open-street-map',
                inline=True,
                style={'margin-top': '10px'}
            )
        ])
    ], style={'padding': '10px'})

    # --- 1. Load data and start playback ---
    @app.callback(
        Output("rms-data", "data"),
        Output("is-playing", "data"),
        Output("play-interval", "disabled"),
        Output("frame-index", "data"),
        Input("start-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def load_rms_data(_):
        url = f"{BASE_URL}/rms_history/{date}"
        try:
            resp = requests.get(url)
            data = resp.json()
            print(f"Loaded {len(data)} time slices from {url}")
            sys.stdout.flush()
            # Enable playback immediately and render the first frame
            return data, True, False, 0
        except Exception as e:
            print("Error fetching data:", e)
            sys.stdout.flush()
            return [], False, True, 0

    # --- 2. Pause and resume controls ---
    @app.callback(
        Output("play-interval", "disabled"),
        Input("pause-btn", "n_clicks"),
        Input("resume-btn", "n_clicks"),
        State("play-interval", "disabled"),
        prevent_initial_call=True
    )
    def toggle_pause(pause_clicks, resume_clicks, disabled):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if button_id == "pause-btn":
            print("Paused playback")
            return True
        elif button_id == "resume-btn":
            print("Resumed playback")
            return False
        raise dash.exceptions.PreventUpdate

    # --- 3. Map update callback ---
    @app.callback(
        Output("map-plot", "figure"),
        Output("map-info", "children"),
        Output("frame-index", "data", allow_duplicate=True),
        Input("play-interval", "n_intervals"),
        State("rms-data", "data"),
        State("frame-index", "data"),
        State("is-playing", "data"),
        State("view-selector", "value"),
        prevent_initial_call=True
    )
    def update_map(n_intervals, data, idx, is_playing, map_style):
        print(f"update_map triggered: n_intervals={n_intervals}, idx={idx}, is_playing={is_playing}")
        sys.stdout.flush()

        if not is_playing or not data:
            fig = px.scatter_mapbox()
            fig.update_layout(mapbox_style=map_style)
            return fig, "Not playing", idx

        idx = (idx or 0) % len(data)
        rms_values = data[idx]

        geom['rms'] = rms_values
        geom['size'] = geom['rms'].apply(lambda x: max(x, 40))

        gdf = gpd.GeoDataFrame(
            geom,
            geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']),
            crs="EPSG:4326"
        )

        fig = px.scatter_mapbox(
            gdf,
            lat=gdf.geometry.y,
            lon=gdf.geometry.x,
            color='rms',
            size='size',
            color_continuous_scale='Viridis',
            range_color=[0, max(gdf['rms'].max(), 1)],
            zoom=11,
            mapbox_style=map_style,
            hover_data={'rms': True, 'channel': True, 'distance': True}
        )

        timestamp = datetime.datetime.strptime(date, "%Y%m%d") + datetime.timedelta(seconds=idx * frame_interval)
        fig.update_layout(
            title=f"RMS Replay – {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            uirevision='map'
        )

        info = f"Frame {idx+1}/{len(data)} – Time: {timestamp.strftime('%H:%M:%S')}"
        next_idx = (idx + 1) % len(data)

        return fig, info, next_idx

    return app


if __name__ == "__main__":
    app = Dash(__name__)
    app = main(app)
    app.run_server(host='0.0.0.0', port=8050, debug=True)
