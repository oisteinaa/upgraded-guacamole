#!/usr/bin/env python

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
from scipy.signal import periodogram
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
from plotly.subplots import make_subplots
import requests
import datetime
from config import cache
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_mastliste, get_weather, get_event_limits

def main(app):
    global geom

    # stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    geom = get_mastliste()
   
    app.layout = html.Div([
        html.Div([
            # dcc.Graph(id=f'gauges', style={'flex': '1 1 20%', 'min-width': '300px'})
        ], 
        style={'padding': '0', 'flex': '1', 'display': 'flex', 'flex-wrap': 'wrap'}),

        html.Div([
            html.Div([
                dcc.Graph(id='live-update-map', style={'height': '80vh', 'margin-top': '10px'}),
                dcc.Interval(
                    id='interval-component',
                    interval=10 * 1000,  # in milliseconds
                    n_intervals=0
                ),
                dcc.RadioItems(
                    id='view-selector',
                    options=[
                        {'label': 'Open street map', 'value': 'open-street-map'},
                        {'label': 'Satellite map', 'value': 'satellite'}
                    ],
                    value='open-street-map',
                    inline=True,
                    style={'margin-top': '20px'}
                ),
                dcc.RadioItems(
                    id='data-selector',
                    options=[
                        {'label': 'RMS', 'value': 'rms'},
                        {'label': 'Variance', 'value': 'var'}
                    ],
                    value='rms',
                    inline=True,
                    style={'margin-top': '20px'}
                ),
                dcc.Store("data_type", storage_type="memory", data="rms"),
                dcc.Store("map_type", storage_type="local", data="open-street-map"),
                dcc.Store("plot_channel", storage_type="local"),

            ], style={'flex': '1', 'flex-direction': 'row','margin-right': '10px'}),
            
            html.Div([
                dcc.Graph(id=f'gauges', style={'flex': '1 1 20%', 'min-width': '300px'}),
                dcc.Graph(id='weather-graph', style={'height': '30vh'}),
                html.Div(id='click-output', style={'margin-top': '20px', 'font-size': '16px'}),
                dcc.Graph(id='plot-channel-graph', style={'height': '30vh'}),
                dcc.RadioItems(
                    id='data-selector-single',
                    options=[
                        {'label': 'Kernel density', 'value': 'kernel'},
                        {'label': 'Spectral density', 'value': 'spectral'}
                    ],
                    value='kernel',
                    inline=True,
                    style={'margin-top': '20px'}
                ),
                dcc.Store("store_data_selector_single", storage_type="local"),
                dcc.Interval(
                    id='interval-component-weather',
                    interval=1700 * 1000,  # in milliseconds
                    n_intervals=0
                ),
            ], style={'flex': '1', 'margin-left': '10px'}),
        ], style={'display': 'flex', 'margin-top': '20px'})
    ], style={'padding': '10px 5px'})

    # Cache the response from the REST server
    @cache.memoize()
    def get_rms_data():
        url = 'http://127.0.0.1:5000/rms'
        url = 'http://10.147.20.10:5000/rms'
        r = requests.get(url)
        return r.json()

    @app.callback(
        Output(f'gauges', 'figure'),
        Input('interval-component', 'n_intervals')
    )
    def update_gauges(n):
        response = get_rms_data()
        event_limits = get_event_limits()
        
        rms_split = response['rms_means']
        
        fig = make_subplots(
            rows=2, cols=4,
            specs=[[{"type": "indicator"}] * 4] * 2
        )
        
        for i, (index, evrow) in enumerate(event_limits.iterrows()):
            # Ensure limit is converted to a numeric type
            limit = float(evrow['limit'])
                
            row = (i // 4) + 1
            col = (i % 4) + 1
            fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                delta={'relative': True},
                value=rms_split[i] if i < len(rms_split) else 0,
                title={'text': evrow['name']},
                gauge={
                'axis': {'range': [0, 1.7*limit]},
                'bar': {'color': "black", "thickness": 0.2},
                'steps': [
                    {'range': [0, limit * 0.7], 'color': "green"},
                    {'range': [limit * 0.7, limit], 'color': "yellow"},
                    {'range': [limit, 1.7*limit], 'color': "red"}
                ]
                }
            ),
            row=row, col=col
            )
        
        fig.update_layout(height=600, title="RMS Gauges")
        return fig

    # Multiple components can update everytime interval gets fired.
    @app.callback(Output('live-update-map', 'figure'),
            Input('interval-component', 'n_intervals'),
            State('map_type', 'data'),
            State('data_type', 'data'),
    )
    def update_graph_live(_, map_type, data_type):
        global geom
        
        if data_type is None:
            data_type = 'rms'
        
        response = get_rms_data()
        rms_json = response[data_type]
        time_stamp = response["time"]

        geom['rms'] = pd.DataFrame(rms_json)
        geom['rms'] = geom['rms'].fillna(20)
        geom['size'] = geom['rms']
        geom['size'] = geom['size'].apply(lambda x: max(x, 40))
        #print(rmsdf)

        if geom['rms'].shape[0] < 1:
            gdf = gpd.GeoDataFrame(geom, geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']), crs="EPSG:4326")
            fig = go.Figure(go.Scattermap(lat=gdf.geometry.y, lon=gdf.geometry.x,
                                            mode='markers',
                                            marker=go.scattermapbox.Marker(
                                                size=14
                                            ),
                                            ))
            fig.update_layout(uirevision='rms', mapbox_style="open-street-map")
            return fig

        gdf = gpd.GeoDataFrame(geom, geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']), crs="EPSG:4326")

        fig = px.scatter_map(
            gdf, 
            lat=gdf.geometry.y, 
            lon=gdf.geometry.x, 
            color='rms', 
            size='size',
            range_color=[0, 10000],
            zoom=11,
            # mapbox_style="open-street-map",
            map_style=map_type,
            hover_data={'rms': True, 'channel': True, 'distance': True, 'gid': True},
            custom_data=['channel', 'rms', 'distance'],
        )
        
        # Add an arrow pointing 88.9 degrees from north
        # direction = 45
        # arrow_start = gdf.geometry.iloc[0]  # Starting point of the arrow
        # arrow_length = 0.1  # Length of the arrow in degrees
        # arrow_end_lat = arrow_start.y + arrow_length * np.cos(np.radians(direction))
        # arrow_end_lon = arrow_start.x + arrow_length * np.sin(np.radians(direction))
        
        # fig.add_trace(go.Scattermapbox(
        #     mode="lines+markers",
        #     lat=[arrow_start.y, arrow_end_lat],
        #     lon=[arrow_start.x, arrow_end_lon],
        #     line=dict(width=2, color="blue"),
        #     marker=dict(size=10, color="blue"),
        #     name="Direction Arrow"
        # ))

        fig.update_layout(
            title=f'Live Data Update {datetime.datetime.fromtimestamp(time_stamp).strftime("%Y-%m-%d %H:%M:%S")}',    
            uirevision='rms'
        )

        return fig
    
    @app.callback(
        Output('weather-graph', 'figure'),
        Input('interval-component-weather', 'n_intervals')
    )
    def update_weather_graph(n):
        response = get_weather()
        # print(response)
        if response.empty:
            return go.Figure()  # Return an empty figure if no data

        # Group the weather data by 'type' and 'lid'
        grouped = response.groupby(['type', 'lid'])

        # Create a scatter plot with one curve per 'type' and 'lid'
        fig = make_subplots(
            rows=1, cols=3, 
            # shared_xaxes=True, 
            subplot_titles=("Temperature", "Wind speed", "Wind direction"),
            vertical_spacing=0.1
        )

        for (type_, lid), group in grouped:
            row = type_  # Assuming 'type_' corresponds to rows 1, 2, 3
            fig.add_trace(
            go.Scatter(
                x=group['time'],
                y=group['value'],
                mode='lines+markers',
                name=f'{type_} - {lid}'
            ),
            row=1, col=row
            )

        fig.update_layout(
            title='Weather Data Over Time',
            xaxis_title='Time',
            yaxis_title='Value',
            height=900,  # Adjust height for three subplots
            uirevision='weather',
            showlegend=False  # Disable legend to avoid clutter
        )

        return fig
    
    def get_single_channel_plot(ch, datatype='kernel'):
        url = f'http://10.147.20.10:5000/channel/{ch}'
        data = requests.get(url).json()
        
        y_data = [item for item in data['data']]
        mean = 0
        std_dev = 0
        if datatype == 'kernel':
            mean = np.mean(y_data)
            std_dev = np.std(y_data)
            x_data = np.linspace(min(y_data), max(y_data), 100)
            y_data_kde = gaussian_kde(y_data)
            y_data = y_data_kde(x_data)
        else:
            # Compute the periodogram using scipy.signal.periodogram
            freqs, power = periodogram(y_data, fs=500)  # Assuming a sampling frequency of 500 Hz

            # Skip the first sample and use frequency and power for the periodogram plot
            x_data = freqs[1:]
            y_data = power[1:]  # Convert power to decibels
        
        
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
            x=x_data,
            y=y_data,
            name=datatype,
            )
        )
        
        # Set the x-axis to logarithmic scale
        
        if datatype == 'kernel':
            # Add a red vertical line at the mean
            fig.add_trace(
                go.Scatter(
                x=[mean, mean],
                y=[0, max(y_data)],
                mode="lines",
                line=dict(color="red", dash="dash"),
                name="Mean"
                )
            )
            
            # Add black vertical lines at plus and minus one standard deviation
            fig.add_trace(
                go.Scatter(
                x=[mean - std_dev, mean - std_dev],
                y=[0, max(y_data)],
                mode="lines",
                line=dict(color="black", dash="dot"),
                name="-1 Std Dev"
                )
            )
            
            fig.add_trace(
                go.Scatter(
                x=[mean + std_dev, mean + std_dev],
                y=[0, max(y_data)],
                mode="lines",
                line=dict(color="black", dash="dot"),
                name="+1 Std Dev"
                )
            )
        else:
            fig.update_xaxes(type="log")
            fig.update_yaxes(type="log")
        
        return fig
    
    @app.callback(Output('plot-channel-graph', 'figure'),
            Input('interval-component', 'n_intervals'),
            State('plot_channel', 'data'),
            State('store_data_selector_single', 'data')
    )
    def update_channel_plot(_, ch, datatype):
        print("Update channel plot", ch)
        if ch is None:
            return go.Figure()
        
        return get_single_channel_plot(ch, datatype)
    
    # Callbacks to store the selected values in dcc.Store
    @app.callback(
        Output('map_type', 'data'),
        Input('view-selector', 'value')
    )
    def store_map_type_value(selected_value):
        print(selected_value)
        return selected_value
    
    @app.callback(
        Output('data_type', 'data'),
        Input('data-selector', 'value')
    )
    def store_data_type_value(selected_value):
        print(selected_value)
        return selected_value
    
    @app.callback(
        Output('store_data_selector_single', 'data'),
        Input('data-selector-single', 'value')
    )
    def store_data_type_value_single(selected_value):
        print(selected_value)
        return selected_value
    
    # New callback to handle click events on the scattermapbox
    @app.callback(
        Output('interval-component', 'n_intervals'),
        Input('live-update-map', 'clickData'),
        State('interval-component', 'n_intervals')
    )
    def trigger_interval(click_data, current_intervals):
        if click_data is None:
            return current_intervals
        
        return current_intervals + 1
    
    @app.callback(
        Output('plot_channel', 'data'),
        Input('live-update-map', 'clickData')
    )
    def store_plot_channel(click_data):
        if click_data is None:
            return None
        
        point_info = click_data['points'][0]
        ch = point_info['customdata'][0]
        return ch
        
        
    @app.callback(
        Output('click-output', 'children'),
        Input('live-update-map', 'clickData')
    )
    def display_click_data(click_data):
        if click_data is None:
            return "Click on a point in the map to see details."
        
        # Extract information from the clicked point
        point_info = click_data['points'][0]
        lat = point_info['lat']
        lon = point_info['lon']
        ch = point_info['customdata'][0]
        # custom_data = point_info.get('customdata', 'N/A')  # If you have custom data
        
        print(point_info)

        return f"Plot Point: Latitude: {lat}, Longitude: {lon}, Channel: {ch}"    
    return app


if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    app.run(debug=True)
