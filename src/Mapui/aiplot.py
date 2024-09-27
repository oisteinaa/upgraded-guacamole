#! /usr/bin/env python3

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import requests
import plotly.graph_objs as go

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

    # Assuming the data is a list of dictionaries with 'x' and 'y' keys
    x_data = [i for i, _ in enumerate(data)]
    y_data = [item for item in data]

    figure = {
        'data': [go.Scatter(
            x=x_data,
            y=y_data,
            mode='lines+markers'
        )],
        'layout': go.Layout(
            title='Live Data Update',
            xaxis={'title': 'X-axis'},
            yaxis={'title': 'Y-axis'}
        ),
    }


    return figure

if __name__ == '__main__':
    app.run_server(debug=True)