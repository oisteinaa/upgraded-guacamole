#!/usr/bin/env python3
import geopandas as gpd
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import requests
import datetime
import time
import dash
from threading import Timer
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
            html.Button("Start Replay", id="start-btn", n_clicks=0),
            dcc.Store(id="rms-data", storage_type="memory"),
            dcc.Store(id="frame-index", storage_type="memory", data=0),
            dcc.Store(id="is-playing", storage_type="memory", data=False),
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

    # Load all data once
    @app.callback(
        Output("rms-data", "data"),
        Input("start-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def load_rms_data(_):
        url = f"{BASE_URL}/rms_history/{date}"
        try:
            resp = requests.get(url)
            data = resp.json()
            print(f"Loaded {len(data)} time slices from {url}")
            return data
        except Exception as e:
            print("Error fetching data:", e)
            return []

    # Start playback
    @app.callback(
        Output("is-playing", "data"),
        Input("rms-data", "data"),
        prevent_initial_call=True
    )
    def start_playback(_):
        return True

    # Sequential rendering logic
    @app.callback(
        Output("map-plot", "figure"),
        Output("map-info", "children"),
        Output("frame-index", "data"),
        Input("frame-index", "data"),
        State("rms-data", "data"),
        State("is-playing", "data"),
        State("view-selector", "value"),
        prevent_initial_call=True
    )
    def update_map(idx, data, is_playing, map_style):
        print(f'Data length: {len(data) if data else 0}, is_playing: {is_playing}, idx: {idx}')
        sys.stdout.flush()
        
        if not is_playing or not data:
            fig = px.scatter_mapbox()
            fig.update_layout(mapbox_style=map_style)
            return fig, "Not playing", idx

        idx = idx or 0
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

        # Schedule next frame render
        next_idx = (idx + 1) % len(data)
        Timer(frame_interval, lambda: app.run_callback("frame-index.data", next_idx)).start()

        return fig, info, next_idx

    return app


# Add a helper to allow scheduling callbacks (Monkeypatch Dash runtime)
def patch_dash_for_timer(app):
    ctx = dash.callback_context

    def run_callback(prop_id, value):
        # Force a property update (simulate frontend change)
        app._callback_list.append((prop_id, value))
        with app.server.test_request_context():
            for cb in app.callback_map.values():
                if cb["output"].component_property == prop_id.split(".")[1]:
                    cb["callback"](value)
    app.run_callback = run_callback

if __name__ == "__main__":
    app = Dash(__name__)
    patch_dash_for_timer(app)
    app = main(app)
    app.run_server(host='0.0.0.0', port=8050, debug=True)
