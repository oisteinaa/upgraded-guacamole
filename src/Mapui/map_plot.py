#!/usr/bin/env python

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import LineString
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import requests
import datetime
from config import cache
import psycopg2

# import sys

def get_mastliste():
    conn = psycopg2.connect(
        dbname="sensnetdb",
        user="sensnetdbu",
        password="obs",
        host="10.147.20.10",
        port="5432"
    )

    # Execute the query and fetch data
    query = """
    WITH numbered_rows AS 
        (SELECT *, row_number() OVER (ORDER BY id) AS rn FROM masteliste)
    SELECT *
    FROM numbered_rows
    WHERE (rn - 1) % 4 = 0 
    AND channel < 33421
    ORDER BY channel DESC 
    LIMIT 8356;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df

def main(app):
    global geom
    
     
    # stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    # Connect to PostgreSQL database
   

    # Close the connection
    geom = get_mastliste()
    # mast_geom = df[['Easting', 'Northing']].values
    #print(mast_geom)
    # ls = LineString(mast_geom)
    # print(ls.length, ls.length / 8334)
    # geom = [ls.interpolate(distance) for distance in np.linspace(0, ls.length, 8334-620)]


    app.layout = html.Div([
        html.Div(children=[
            dcc.Graph(id=f'gauge-{i+1}', style={'flex': '1 1 20%', 'min-width': '300px'}) for i in range(8)
        ], 
        style={'padding': '0', 'flex': '1', 'display': 'flex', 'flex-wrap': 'wrap'}),

        html.Div([   
            dcc.Graph(id='live-update-map', style={'height': '60vh', 'margin-top': '10px'}),
            dcc.Interval(
                id='interval-component',
                interval=10 * 1000,  # in milliseconds
                n_intervals=0
            ),
            html.Div(id='click-output', style={'margin-top': '20px', 'font-size': '16px'})

        ])
    ], style={'padding': '10px 5px'})

    # Cache the response from the REST server
    @cache.memoize()
    def get_rms_data():
        url = 'http://127.0.0.1:5000/rms'
        r = requests.get(url)
        return r.json()

    @app.callback(
        [Output(f'gauge-{i+1}', 'figure') for i in range(8)],
        Input('interval-component', 'n_intervals')
    )
    def update_gauges(n):
        response = get_rms_data()
        rms_split = response['rms_means']
        
        gauges = []
        for i in range(8):
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                delta = {'relative': True},
                value=rms_split[i],
                gauge={
                    'axis': {'range': [None, 4000]},
                    'bar': {'color': "black", "thickness": 0.2},
                    'steps': [
                        {'range': [0, 2500], 'color': "green"},
                        {'range': [2500, 3500], 'color': "yellow"},
                        {'range': [3500, 4000], 'color': "red"}
                    ]
                }
            ))
            fig.update_layout(height=250)
            gauges.append(fig)
        
        return gauges

    # Multiple components can update everytime interval gets fired.
    @app.callback(Output('live-update-map', 'figure'),
            Input('interval-component', 'n_intervals'))
    def update_graph_live(_):
        global geom
        
        response = get_rms_data()
        rms_json = response['rms']
        time_stamp = response["time"]

        geom['rms'] = pd.DataFrame(rms_json)
        geom['rms'] = geom['rms'].fillna(20)
        #print(rmsdf)

        if geom['rms'].shape[0] < 1:
            gdf = gpd.GeoDataFrame(geom, geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']), crs="EPSG:4326")
            fig = go.Figure(go.Scattermapbox(lat=gdf.geometry.y, lon=gdf.geometry.x,
                                            mode='markers',
                                            marker=go.scattermapbox.Marker(
                                                size=14
                                            ),
                                            ))
            fig.update_layout(uirevision='rms', mapbox_style="open-street-map")

            return fig

        # if len(rmsdf) != len(geom):
        #     geom = [ls.interpolate(distance) for distance in np.linspace(0, ls.length, len(rmsdf))]
            
        # gdf = gpd.GeoDataFrame(geom, geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']), crs="EPSG:32633")
        gdf = gpd.GeoDataFrame(geom, geometry=gpd.points_from_xy(geom['longitude'], geom['latitude']), crs="EPSG:4326")
        #print(np.multiply(range(0, rmsdf.shape[1]), ls.length / rmsdf.shape[1]))
        # gdf = gdf.to_crs(crs="EPSG:4326")

        fig = px.scatter_mapbox(
            gdf, 
            lat=gdf.geometry.y, 
            lon=gdf.geometry.x, 
            color='rms', 
            size='rms',
            range_color=[5500, 18000],
            zoom=11,
            mapbox_style="open-street-map",
            hover_data={'rms': True, 'channel': True, 'distance': True}
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
    
    # New callback to handle click events on the scattermapbox
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
        ch = point_info['channel']
        # custom_data = point_info.get('customdata', 'N/A')  # If you have custom data
        
        print(f"Clicked Point: Latitude: {lat}, Longitude: {lon}")

        return f"Clicked Point: Latitude: {lat}, Longitude: {lon}, Channel: {ch}"

    
    return app


if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    app.run(debug=True)
