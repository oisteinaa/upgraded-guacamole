#! /usr/bin/env python3

import requests
import numpy as np
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
from config import cache

# Initialize rms_data_list with 50 arrays of zeroes
rms_data_list = [np.zeros(14874) for _ in range(50)]
old_time = 0



def main(app):
    app.layout = html.Div([
        dcc.Graph(id='rms-graph'),
        dcc.Interval(
            id='interval-component',
            interval=5*1000,  # in milliseconds
            n_intervals=0
        ),
        dcc.Store(id='interval-state', data={'running': True})
    ])

    # Cache the response from the REST server
    @cache.memoize()
    def get_rms_data():
        url = 'http://localhost:5000/rms'
        r = requests.get(url)
        return r.json()
    
    @app.callback(
        Output('interval-state', 'data'),
        [Input('interval-component', 'n_intervals')],
        [State('interval-state', 'data')]
    )
    def update_interval_state(n_intervals, interval_state):
        if interval_state['running']:
            return {'running': False}
        return interval_state

    @app.callback(
        Output('rms-graph', 'figure'),
        [Input('interval-state', 'data')]
    )
    def update_plot(interval_state):
        global old_time
        
        # print((rms_data_list))
        if not interval_state['running']:
            data = get_rms_data()
            if data['time'] <= old_time:
                return go.Figure(data=go.Heatmap(
                    z=np.array(rms_data_list),
                    colorscale='Viridis'
                ))
            
            old_time = data['time']
            
            rms_values = data['rms']
            print(len(rms_values))
            rms_data_list.append(rms_values)
            
            # Ensure rms_data_list maintains a fixed size of 50 arrays
            if len(rms_data_list) > 50:
                rms_data_list.pop(0)
            
            fig = go.Figure(data=go.Heatmap(
                z=np.array(rms_data_list),
                colorscale='Viridis'
            ))
            
            fig.update_layout(height=800, uirevision='rms')
            
            return fig

        return go.Figure(data=go.Heatmap(
            z=np.array(rms_data_list),
            colorscale='Viridis'
        ))
    return app

if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    
    app.run_server(debug=True, host='0.0.0.0')
