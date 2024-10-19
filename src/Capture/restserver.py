#! /usr/bin/env python3

from flask import Flask, jsonify, request, Response
import json

app = Flask(__name__)

RMS = {'rms': [], 'var': [], 'data': []}  
DATA = None

@app.route('/rms')
def get_rms():
    return jsonify(RMS)

@app.route('/rawdata')
def get_data():
    global DATA
    return Response(DATA, content_type='application/octet-stream')


@app.route('/rms', methods=['POST'])
def add_rms():
    global RMS
    rms_json = request.get_json()
    RMS = json.loads(rms_json)
    return '', 204

@app.route('/rawdata', methods=['POST'])
def add_data():
    global DATA
    DATA = request.data

    return '', 204


if __name__ == '__main__':
    app.run(debug=True)