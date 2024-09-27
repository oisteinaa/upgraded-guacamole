#! /usr/bin/env python3

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import requests
import plotly.graph_objs as go
from plotly.subplots import make_subplots

app = dash.Dash(__name__)

app.layout = html.Div([
    dcc.Graph(id='live-update-graph'),
    dcc.Interval(
        id='interval-component',
        interval=5*1000,  # in milliseconds
        n_intervals=0
    )
])

@app.callback(Output('live-update-graph', 'figure'),
              Input('interval-component', 'n_intervals'))
def update_graph_live(n):
    # Replace with your REST API endpoint
    url = 'http://localhost:5000/rms'
    response = requests.get(url)
    data = response.json()["rms"]
    var = response.json()["var"]

    # Assuming the data is a list of dictionaries with 'x' and 'y' keys
    x_data = [i for i, _ in enumerate(data)]
    y_data = [item for item in data]
    y_var = [item for item in var]

    # Create subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=('RMS', 'VAR'))

    # Add traces
    fig.add_trace(
        go.Scatter(
            x=x_data,
            y=y_data,
            mode='lines+markers',
            name='RMS'
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_data,
            y=y_var,
            mode='lines+markers',
            name='VAR'
        ),
        row=2, col=1
    )

    # Update layout
    fig.update_layout(
        title='Live Data Update',
        xaxis_title='X-axis',
        yaxis_title='Y-axis',
        uirevision='constant'  # Add uirevision to maintain zoom level
    )

    return fig

if __name__ == '__main__':
    app.run_server(debug=True)