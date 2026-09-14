#!/usr/bin/env python

import sys
import os
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, dash_table
from dash.dependencies import Input, Output

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_event_locations


def main(app):
    app.layout = html.Div([
        html.H1("Event Map & Timeline"),
        dcc.Graph(id='event-map', style={'height': '60vh'}),
        dcc.Graph(id='event-timeline', style={'height': '30vh'}),
        dcc.Interval(
            id='event-interval',
            interval=30 * 1000,  # in milliseconds
            n_intervals=0
        ),
        html.H3("Recent events"),
        dash_table.DataTable(
            id='event-table',
            page_size=15,
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left'},
        ),
    ], style={'padding': '10px 20px'})

    @app.callback(
        Output('event-map', 'figure'),
        Output('event-timeline', 'figure'),
        Output('event-table', 'columns'),
        Output('event-table', 'data'),
        Input('event-interval', 'n_intervals'),
    )
    def update_events(_):
        events = get_event_locations(limit=200)

        if events.empty:
            return go.Figure(), go.Figure(), [], []

        located = events.dropna(subset=['latitude', 'longitude']).copy()
        if located.empty:
            map_fig = go.Figure()
        else:
            located['size'] = located['value'].abs().clip(lower=1)
            map_fig = px.scatter_map(
                located,
                lat='latitude',
                lon='longitude',
                color='type',
                size='size',
                zoom=11,
                map_style='open-street-map',
                hover_data={'time': True, 'comment': True, 'value': True, 'size': False},
            )
            map_fig.update_layout(title='Recent events along the line', uirevision='events')

        timeline_fig = px.scatter(
            events,
            x='time',
            y='value',
            color='type',
            hover_data=['comment'],
        )
        timeline_fig.update_layout(title='Event magnitude over time', uirevision='events-timeline')

        table = events.drop(columns=['name'], errors='ignore')
        columns = [{"name": col, "id": col} for col in table.columns]
        return map_fig, timeline_fig, columns, table.to_dict('records')

    return app


if __name__ == '__main__':
    app = Dash(__name__)
    app = main(app)
    app.run(debug=True)
