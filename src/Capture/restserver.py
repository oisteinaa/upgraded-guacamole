#! /usr/bin/env python3

from flask import Flask, jsonify, request, Response
import json
import msgpack
import numpy as np
import os
import sys

app = Flask(__name__)

RMS = {'rms': [], 'var': [], 'data': []}  
DATA = None
DATA_PREFIX = '/raid1/sensnet_data'

@app.route('/rms')
def get_rms():
    return jsonify(RMS)

@app.route('/rms_history/<date>')
def get_rms_history(date):
    year = date[0:4]
    month = date[4:6]
    day = date[6:8]
    directory = f'{DATA_PREFIX}/rms/{year}/{month}/{day}'
    files = sorted([f for f in os.listdir(directory) if f.endswith('.json')])
    
    RMS = []
    for fname in files:
        with open(os.path.join(directory, fname), 'r') as f:
            data = json.load(f)
            RMS.extend(data)
            
    return jsonify(RMS)

@app.route('/rawdata')
def get_data():
    return Response(DATA, content_type='application/octet-stream')

@app.route('/channel/<int:channel_id>', methods=['GET'])
def get_channel_data(channel_id):
    channel_id = int(int(channel_id)/4)    
    buf = msgpack.unpackb(DATA, raw=False)
    shape = buf['shape']
    data = np.array(buf['data']).reshape(shape)
    
    
    print('Shape', data.shape)  
    
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