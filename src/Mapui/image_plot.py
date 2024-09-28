#!/usr/bin/env python3  

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import numpy as np
import plotly.graph_objs as go
import requests
from scipy.signal import periodogram

# Sample data for demonstration
# data = np.random.rand(100, 100)

# Create a Dash app
app = dash.Dash(__name__)

# Create a figure using Plotly Graph Objects
url = 'http://localhost:5000/rms'
response = requests.get(url)
data = np.array(response.json()["data"])

# Create the initial heatmap figure
heatmap_fig = go.Figure(data=go.Heatmap(z=data, colorscale='Gray', zmin=-1000, zmax=1000))
heatmap_fig.update_layout(height=800)  # Adjust the height as needed

# Define the layout of the app
app.layout = html.Div(children=[
    html.H1(children='Image Plot'),

    dcc.Graph(
        id='heatmap-graph',
        figure=heatmap_fig
    ),

    html.Label('Select Channel:'),
    dcc.Dropdown(
        id='column-selector',
        options=[{'label': f'CHannel {i}', 'value': i} for i in range(data.shape[1])],
        value=0
    ),

    dcc.Graph(
        id='periodogram-graph'
    )
])

# Define the callback to update the periodogram based on the selected column
@app.callback(
    Output('periodogram-graph', 'figure'),
    [Input('column-selector', 'value')]
)
def update_periodogram(selected_column):
    # Extract the selected column data
    column_data = data[:, selected_column]

    # Compute the periodogram
    freqs, power = periodogram(column_data)

    # Create the periodogram figure
    periodogram_fig = go.Figure(data=go.Scatter(x=freqs, y=power, mode='lines'))
    periodogram_fig.update_layout(title=f'Periodogram of Channel {selected_column}',
                                  xaxis_title='Frequency',
                                  yaxis_title='Power')

    return periodogram_fig

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)