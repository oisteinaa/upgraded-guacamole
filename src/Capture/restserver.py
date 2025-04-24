#! /usr/bin/env python3

from flask import Flask, jsonify, request, Response
import json
import msgpack
import numpy as np

app = Flask(__name__)

RMS = {'rms': [], 'var': [], 'data': []}  
DATA = None

@app.route('/rms')
def get_rms():
    return jsonify(RMS)

@app.route('/rawdata')
def get_data():
    return Response(DATA, content_type='application/octet-stream')

@app.route('/channel/<int:channel_id>', methods=['GET'])
def get_channel_data(channel_id):    
    buf = msgpack.unpackb(DATA, raw=False)
    shape = buf['shape']
    data = np.array(buf['data']).reshape(shape)
    
    channel_data = {
        'data': data[:, channel_id].tolist()
    }
    return jsonify(channel_data)
    
        
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
    app.run(debug=True, host='0.0.0.0', port=5000)