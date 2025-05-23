#!/usr/bin/env python3  

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import numpy as np
import plotly.graph_objs as go
import requests
import msgpack
from scipy.signal import periodogram
from config import cache

# Sample data for demonstration
# data = np.random.rand(100, 100)

# Create a Dash app
# app = dash.Dash(__name__)

LAST_TIME = "" 


def main(app):
    global LAST_TIME
    
    @cache.memoize()
    def get_data(url):
        r = requests.get(url)
        return r

    data = None
    # Create a figure using Plotly Graph Objects
    # url = 'http://localhost:5000/rawdata'

    # response = get_data(url)
    # print(response)
    # buf = msgpack.unpackb(response.content, raw=False)
    # shape = buf['shape'] 
    # data = np.array(buf['data']).reshape(shape)

    # if data.size == 0:
    #     return

    # print('Shape', data.shape)

    # Create the initial heatmap figure
    # heatmap_fig = go.Figure(data=go.Heatmap(z=data, colorscale='Gray', zmin=-1000, zmax=1000))
    # heatmap_fig.update_layout(height=800)  # Adjust the height as needed

    # Define the layout of the app
    app.layout = html.Div(children=[
        html.H1(children='Image Plot'),

        dcc.Graph(
            id='heatmap-graph',
            figure=go.Figure()
        ),

        html.Label('Select Channel:'),
        dcc.Dropdown(
            id='column-selector',
            options=[{'label': f'Channel {i}', 'value': i} for i in range(3000)],
            value=0
        ),

        dcc.Graph(
            id='periodogram-graph'
        ),
        dcc.Interval(
            id='interval-component',
            interval=10*1000,  # in milliseconds
            n_intervals=0
        )
    ])

    @app.callback(Output('heatmap-graph', 'figure'),
                Input('interval-component', 'n_intervals'))
    def update_graph_live(n):
        global LAST_TIME, data
        # Replace with your REST API endpoint
        url = 'http://10.147.20.10:5000/rawdata'
        response = get_data(url)

        # if "time" not in response.json():
        #     return

        # time_stamp = response.json()["time"]

        # if time_stamp == LAST_TIME:
        #     print("No new data", time_stamp, LAST_TIME)
        #     LAST_TIME = time_stamp
        #     return
    
        buf = msgpack.unpackb(response.content, raw=False)
        # buf = response.content
        shape = buf['shape']
        dx = buf['dx'] 
        data = np.array(buf['data']).reshape(shape)

        # x_data = [f'{i*dx/1000:.2f} km' for i in range(200)]
        # x_data = ['0 km', f'{dx*shape[0]/2} km', f'{dx*shape[0]} km']
        
        # print(x_data)

        # Create the initial heatmap figure
        heatmap_fig = go.Figure(data=go.Heatmap(z=data, colorscale='Gray', zmin=-1000, zmax=1000))
        #heatmap_fig.update_xaxes(title_text='X Axis', tickvals=list(range(len(x_data))), ticktext=x_data)
        heatmap_fig.update_layout(height=800)  # Adjust the height as needed

        return heatmap_fig

    # Define the callback to update the periodogram based on the selected column
    @app.callback(
        Output('periodogram-graph', 'figure'),
        [Input('column-selector', 'value')]
    )
    def update_periodogram(selected_column):
        # Extract the selected column data
        global data
        if data is None:
            return go.Figure()
        
        column_data = data[:, selected_column]

        # Compute the periodogram
        freqs, power = periodogram(column_data, fs=500)

        # Create the periodogram figure
        periodogram_fig = go.Figure(data=go.Scattergl(x=freqs, y=power, mode='lines'))
        periodogram_fig.update_layout(title=f'Periodogram of Channel {selected_column}',
                                    xaxis_title='Frequency',
                                    yaxis_title='Power')

        return periodogram_fig
    return app

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)