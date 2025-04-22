import dash
from dash import Dash, html, dash_table
import pandas as pd

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_event_data

def main(app):
    # Fetch data
    event_data = get_event_data()

    # Layout
    app.layout = html.Div([
        html.H1("Event Log Table"),
        dash_table.DataTable(
            id='event-table',
            columns=[{"name": col, "id": col} for col in event_data.columns],
            data=event_data.to_dict('records'),
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left'},
        )
    ])
    
    return app

# Run the app
if __name__ == '__main__':
    app = Dash(__name__)
    print(app)
    app = main(app)
    app.run(debug=True)