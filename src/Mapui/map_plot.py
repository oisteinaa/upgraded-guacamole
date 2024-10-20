#!/usr/bin/env python

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import LineString
from dash import dcc, html
from dash.dependencies import Input, Output
import requests
from flask_caching import Cache

# import sys

def main(app):
    global geom
    
    cache = Cache(app.server, config={
        'CACHE_TYPE': 'simple',  # You can use 'redis' or 'memcached' for production
        'CACHE_DEFAULT_TIMEOUT': 9  # Cache timeout in seconds
    })
     
    # stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
    df = pd.read_excel('../../Masteliste R12 Svolvar_Kleppstad.xlsx')
    mast_geom = df[['Easting', 'Northing']].values
    #print(mast_geom)
    ls = LineString(mast_geom)
    print(ls.length, ls.length / 14874)
    geom = [ls.interpolate(distance) for distance in np.linspace(0, ls.length, 14874)]


    app.layout = html.Div(
        html.Div([
            dcc.Graph(id='live-update-map', style={'width': '90vh', 'height': '90vh'}),
            dcc.Interval(
                id='interval-component',
                interval=10 * 1000,  # in milliseconds
                n_intervals=0
            )
        ])
    )
    
    # Cache the response from the REST server
    @cache.memoize()
    def get_rms_data():
        url = 'http://127.0.0.1:5000/rms'
        r = requests.get(url)
        return r.json()


    # Multiple components can update everytime interval gets fired.
    @app.callback(Output('live-update-map', 'figure'),
            Input('interval-component', 'n_intervals'))
    def update_graph_live(_):
        global geom
        
        rms_json = get_rms_data()['rms']

        rmsdf = pd.DataFrame(rms_json)
        rmsdf.columns = ['rms']
        #print(rmsdf)

        if rmsdf.shape[0] < 1:
            gdf = gpd.GeoDataFrame(geometry=geom, crs="EPSG:32633")
            fig = go.Figure(go.Scattermapbox(lat=gdf.geometry.y, lon=gdf.geometry.x,
                                            mode='markers',
                                            marker=go.scattermapbox.Marker(
                                                size=14
                                            ),
                                            ))
            fig.update_layout(uirevision='rms', mapbox_style="open-street-map")

            return fig

        if len(rmsdf) != len(geom):
            geom = [ls.interpolate(distance) for distance in np.linspace(0, ls.length, len(rmsdf))]
            
        gdf = gpd.GeoDataFrame(rmsdf, geometry=geom, crs="EPSG:32633")
        #print(np.multiply(range(0, rmsdf.shape[1]), ls.length / rmsdf.shape[1]))
        gdf = gdf.to_crs(crs="EPSG:4326")

        fig = px.scatter_mapbox(gdf, lat=gdf.geometry.y, lon=gdf.geometry.x, color='rms', size='rms',
                                range_color=[1500, 6000],
                                zoom=11,
                                mapbox_style="open-street-map")
        fig.update_layout(uirevision='rms')

        return fig
    
    return app


if __name__ == '__main__':

    app.run(debug=True)
