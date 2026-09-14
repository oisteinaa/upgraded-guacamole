#! /usr/bin/env python3

from flask import Flask, render_template
from flask_caching import Cache
import dash
import aiplot
import image_plot
import map_plot
import rms_strip
import event_log
import event_map
import trend_view
import history_playback
from config import app


print("Initializing dash apps")
# Initialize Dash app for RMS
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

print("Initializing rms app")
rms_app = dash.Dash("rms_app", server=app, url_base_pathname='/rms/')
aiplot.main(rms_app)

print("Initializing rms app")     
rms_strip_app = dash.Dash("rms_strip_app", server=app, url_base_pathname='/rms_strip/')
rms_strip.main(rms_strip_app)

print("Initializing image app")
image_app = dash.Dash("image_app", server=app, url_base_pathname='/data/')
image_plot.main(image_app)

print("Initializing map app")
map_app = dash.Dash("map_app", server=app, url_base_pathname='/maps/', external_stylesheets=external_stylesheets)
map_plot.main(map_app)

print("Initializing event log app")
event_log_app = dash.Dash("event_log_app", server=app, url_base_pathname='/event_log/')
event_log.main(event_log_app)

print("Initializing event map app")
event_map_app = dash.Dash("event_map_app", server=app, url_base_pathname='/event_map/', external_stylesheets=external_stylesheets)
event_map.main(event_map_app)

print("Initializing trend app")
trend_app = dash.Dash("trend_app", server=app, url_base_pathname='/trend/', external_stylesheets=external_stylesheets)
trend_view.main(trend_app)

print("Initializing history app")
history_app = dash.Dash("history_app", server=app, url_base_pathname='/history/', external_stylesheets=external_stylesheets)
history_playback.main(history_app)
print("Dash apps initialized")

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/rms')
def rms():
    return rms_app.index()

@app.route('/rms_strip')
def rms_strip():
    return rms_strip_app.index()

@app.route('/data')
def data():
    return image_app.index()

@app.route('/maps')
def maps():
    return map_app.index()

@app.route('/event_log')
def event_log():
    return event_log_app.index()

@app.route('/event_map')
def event_map_route():
    return event_map_app.index()

@app.route('/trend')
def trend_route():
    return trend_app.index()

@app.route('/history')
def history_route():
    return history_app.index()

if __name__ == '__main__':
    print("Running app")
    app.run(host='0.0.0.0', port=8051, debug=False)
