#! /usr/bin/env python3

from flask import Flask, render_template
from flask_caching import Cache
import dash
import aiplot
import image_plot
import map_plot
import rms_strip
from config import app


print("Initializing dash apps")
# Initialize Dash app for RMS

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
map_app = dash.Dash("map_app", server=app, url_base_pathname='/maps/')
map_plot.main(map_app)

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

if __name__ == '__main__':
    print("Running app")
    app.run(host='0.0.0.0', port=8050, debug=False)
