import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import LineString
from dash import Dash, dcc, html, Input, Output, callback
import requests
import json
# import sys

# stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
df = pd.read_excel('../../Masteliste R12 Svolvar_Kleppstad.xlsx')
print(df[['Easting', 'Northing']])
ls = LineString(df[['Easting', 'Northing']])
print(ls.length, ls.length / 6250)
geom = (ls.interpolate(np.multiply(range(0, 6250), ls.length / 6250)))

app = Dash(__name__)

app.layout = html.Div(
    html.Div([
        dcc.Graph(id='live-update-graph', style={'width': '90vh', 'height': '90vh'}),
        dcc.Interval(
            id='interval-component',
            interval=10 * 500,  # in milliseconds
            n_intervals=0
        )
    ])
)


# Multiple components can update everytime interval gets fired.
@callback(Output('live-update-graph', 'figure'),
          Input('interval-component', 'n_intervals'))
def update_graph_live(_):
    url = 'http://127.0.0.1:5000/rms'
    r = requests.get(url)
    print(r.json())
    rms_json = r.json()

    rmsdf = pd.DataFrame(rms_json)
    print(rmsdf)

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

    gdf = gpd.GeoDataFrame(rmsdf, geometry=geom, crs="EPSG:32633")
    print(np.multiply(range(0, rmsdf.shape[0]), ls.length / rmsdf.shape[0]))
    gdf = gdf.to_crs(crs="EPSG:4326")

    fig = px.scatter_mapbox(gdf, lat=gdf.geometry.y, lon=gdf.geometry.x, color='rms', size='rms',
                            range_color=[20, 30],
                            zoom=11,
                            mapbox_style="open-street-map")
    fig.update_layout(uirevision='rms')

    return fig


if __name__ == '__main__':
    app.run(debug=True)
