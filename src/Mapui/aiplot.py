#! /usr/bin/env python3

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import requests
import datetime
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from config import cache

LAST_TIME = ""


def main(app):
    global LAST_TIME

    app.layout = html.Div([
        dcc.Graph(id='live-update-graph'),
        dcc.Interval(
            id='interval-component',
            interval=10*1000,  # in milliseconds
            n_intervals=0
        )
    ])
    

    # Cache the response from the REST server
    @cache.memoize()
    def get_rms_data():
        url = 'http://localhost:5000/rms'
        r = requests.get(url)
        return r.json()
    

    @app.callback(Output('live-update-graph', 'figure'),
                Input('interval-component', 'n_intervals'))
    def update_graph_live(n):
        global LAST_TIME

        response = get_rms_data()
        
        if "time" not in response:
            print("No time in response")
            return
        
        time_stamp = response["time"]

        if time_stamp == LAST_TIME:
            print("No new data", time_stamp, LAST_TIME)
            LAST_TIME = time_stamp
            return
    
        data = response["rms"]
        var = response["var"]
        dx = response["dx"]

        # Assuming the data is a list of dictionaries with 'x' and 'y' keys
        x_data = [i*dx for i, _ in enumerate(data)]
        y_data = [item for item in data]
        y_var = [item for item in var]

        print(len(x_data), len(y_data), len(y_var))

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
            template='plotly',  # Ensure this is a valid template name
            title=f'Live Data Update {datetime.fromtimestamp(time_stamp).strftime("%Y-%m-%d %H:%M:%S")}',
            xaxis_title='X-axis',
            yaxis_title='Y-axis',
            uirevision='constant'  # Add uirevision to maintain zoom level
        )

        # print(fig, )

        return fig
    return app

if __name__ == '__main__':
    app = dash.Dash(__name__, server=server_app, url_base_pathname='/rms/')
    app = main(app)
    app.run_server(debug=True)