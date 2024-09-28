#! /usr/bin/env python3

from flask import Flask, render_template
import dash
import aiplot
import image_plot

app = Flask(__name__)

# Initialize Dash app for RMS
rms_app = dash.Dash("rms_app", server=app, url_base_pathname='/rms/')
aiplot.main(rms_app)

image_app = dash.Dash("image_app", server=app, url_base_pathname='/data/')
image_plot.main(image_app)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/rms')
def rms():
    return rms_app.index()

@app.route('/data')
def data():
    return image_app.index()

if __name__ == '__main__':
    app.run(port=8050, debug=True)