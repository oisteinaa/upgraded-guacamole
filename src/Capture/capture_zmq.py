#!/usr/bin/env python3

import zmq
import time
from multiprocessing import Process
import h5py
import numpy as np
import requests
import json
import msgpack
import zstandard as zstd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_mastliste
from concurrent.futures import ThreadPoolExecutor
from event_detector import detect_events

def compress_data(data, compression_level=22):
    """
    Compress binary data using Zstandard with lossy compression.
    """
    # Convert data to a lossy format (e.g., reduce precision)
    lossy_data = np.round(data, decimals=2)  # Reduce precision to 2 decimal places
    serialized = msgpack.packb(lossy_data.tolist())  # Serialize the data

    # Compress using Zstandard
    compressor = zstd.ZstdCompressor(level=compression_level)
    compressed = compressor.compress(serialized)
    return compressed

def get_rms(data):
    return np.sqrt(np.mean(np.square(data), axis=0)).tolist()
    
def get_variance(data):
    return np.var(data, axis=0).tolist()

def get_rms_chunks(rms, mastdf):
    rms_means = []
    for gid in mastdf['gid'].unique():
        indices = mastdf[mastdf['gid'] == gid].index
        rms_chunk = [rms[i] for i in indices if i < len(rms)]
        if rms_chunk:
            rms_means.append(np.mean(rms_chunk))
            
    return rms_means


def process_data(file, mastdf):
    tries = 50
    while tries:
        try:
            f = h5py.File(file, 'r')
            break
        except:
            print(f"Retry {tries}")
            tries -= 1
            time.sleep(1)

    if tries == 0:
        return

    rms = []
    data = f['data']
    data = data.astype(np.float32)
    # Reverse the order of data on axis=1
    data = np.flip(data, axis=1)
    data = np.divide(data, f['header']['sensitivities'][0])
    
    with ThreadPoolExecutor() as executor:
        rms_future = executor.submit(get_rms, data)
        var_future = executor.submit(get_variance, data)
        rms_means_future = executor.submit(get_rms_chunks, rms_future.result(), mastdf)

        rms = rms_future.result()
        var = var_future.result()
        rms_means = rms_means_future.result()
        
    # Run detect_events in a separate thread
    thread = ThreadPoolExecutor(max_workers=1)
    thread.submit(detect_events, rms_means)
 

    url = 'http://127.0.0.1:5000/rms'
    rms_json = {
        'time': time.time(), 
        'dx': f['cableSpec']['sensorDistances'][1],
        'rms': rms, 'var': var, 
        'rms_means': rms_means,
        # 'data': data[:, 1:350].tolist()
    }
    headers = {
        'Content-type': 'application/json',
        'Accept': 'application/json'
    }
    requests.post(url, json=json.dumps(rms_json), headers=headers)
    
    url = 'http://127.0.0.1:5000/rawdata'
    headers = {'Content-Type': 'application/octet-stream'}

    # Include the shape of the data in the payload
    data = f['data'][:, :]
    data.astype(np.int16)
    # serialized = msgpack.packb(data.tolist())
    # compressed = compress_data(data, compression_level=22)
    payload = {
        'dx': f['cableSpec']['sensorDistances'][1],
        'shape': data.shape,
        'data': data.tolist()
    }
    
    # Serialize the payload using msgpack
    serialized_payload = msgpack.packb(payload)
    
    requests.post(url, data=serialized_payload, headers=headers)
 
 
def zmq_server():
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind("tcp://*:12345")

    print("Server is listening on port 12345...")

    df = get_mastliste()
    
    while True:
        message = socket.recv_json()
        process_data(message['dest_path'], df)
        print(f"Received message: {message}")

if __name__ == "__main__":
    zmq_server()