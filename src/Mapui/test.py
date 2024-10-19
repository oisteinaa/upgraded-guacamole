import plotly.graph_objects as go
import plotly.io as pio

# Define the figure
fig = go.Figure({
    'data': [{'mode': 'lines+markers',
              'name': 'RMS',
              'type': 'scatter',
              'x': list(range(6)),  # Assuming the x values are a range from 0 to 4275
              'y': [118.4960708618164, 57.065547943115234, 74.3692626953125, 
                    # ... (other y values for RMS)
                    1199.2999267578125, 1186.4195556640625, 1114.45703125],
              'xaxis': 'x',
              'yaxis': 'y'},
             {'mode': 'lines+markers',
              'name': 'VAR',
              'type': 'scatter',
              'x': list(range(6)),  # Assuming the x values are a range from 0 to 4275
              'y': [-0.04879999905824661, 0.020239999517798424,
                    -0.04684000089764595, 
                    # ... (other y values for VAR)
                    -2.716360092163086, 3.9627199172973633, 2.073280096054077],
              'xaxis': 'x2',
              'yaxis': 'y2'}],
    'layout': {'annotations': [{'font': {'size': 16},
                                'showarrow': False,
                                'text': 'RMS',
                                'x': 0.5,
                                'xanchor': 'center',
                                'xref': 'paper',
                                'y': 1.0,
                                'yanchor': 'bottom',
                                'yref': 'paper'},
                               {'font': {'size': 16},
                                'showarrow': False,
                                'text': 'VAR',
                                'x': 0.5,
                                'xanchor': 'center',
                                'xref': 'paper',
                                'y': 0.375,
                                'yanchor': 'bottom',
                                'yref': 'paper'}],
               'template': 'plotly_dark',
               'xaxis': {'anchor': 'y', 'domain': [0.0, 1.0], 'matches': 'x2', 'showticklabels': False},
               'xaxis2': {'anchor': 'y2', 'domain': [0.0, 1.0]},
               'yaxis': {'anchor': 'x', 'domain': [0.625, 1.0]},
               'yaxis2': {'anchor': 'x2', 'domain': [0.0, 0.375]}}
})

# Validate and show the figure
pio.show(fig, validate=True)