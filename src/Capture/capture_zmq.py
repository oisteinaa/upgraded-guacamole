#!/usr/bin/env python3

import zmq
import time
from multiprocessing import Process
import h5py
import numpy as np
import numexpr as ne
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
import re

DATA_PREFIX = '/raid1/sensnet_data/'
GET_DATE = re.compile(r'/(\d{8})/')

def unwrap(phi, wrapStep=2*np.pi, axis=-1):
    scale = 2*np.pi/wrapStep

    return (np.unwrap(phi*scale, axis=axis)/scale).astype(phi.dtype)

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

def get_date(filename):
    # Find the date part in the path (expects /YYYYMMDD/ somewhere in the path)
    # Use a globally compiled regex for performance
    match = GET_DATE.search(filename)

    if match:
        date_str = match.group(1)
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
    else:
        # Fallback to current date if not found
        year = time.strftime("%Y")
        month = time.strftime("%m")
        day = time.strftime("%d")

    return year, month, day

def get_rms(data, filename=None):
    rms = np.sqrt(np.mean(np.square(data), axis=0)).tolist()
    year, month, day = get_date(filename)
    directory = f'{DATA_PREFIX}rms/{year}/{month}/{day}'
    filename = os.path.basename(filename).replace('.hdf5','')
    
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    
    if filename:
        with open(f"{directory}/{filename}_rms.json", "w") as f:
            json.dump(rms, f)
    return rms

def get_variance(data, filename=None):
    var = np.var(data, axis=0).tolist()
    year, month, day = get_date(filename)
    directory = f'{DATA_PREFIX}variance/{year}/{month}/{day}'
    filename = os.path.basename(filename).replace('.hdf5','')
    
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    
    if filename:
        with open(f"{directory}/{filename}_var.json", "w") as f:
            json.dump(var, f)
    return var

def get_rms_chunks(rms, mastdf, filename=None):
    rms_means = []
    year, month, day = get_date(filename)
    directory = f'{DATA_PREFIX}rms_means/{year}/{month}/{day}'
    filename = os.path.basename(filename).replace('.hdf5','')
    
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        
    for gid in mastdf['gid'].unique():
        indices = mastdf[mastdf['gid'] == gid].index
        rms_chunk = [rms[i] for i in indices if i < len(rms)]
        if rms_chunk:
            rms_means.append(np.mean(rms_chunk))
    if filename:
        with open(f"{directory}/{filename}_rms_means.json", "w") as f:
            json.dump(rms_means, f)
            
    return rms_means


def process_data(file, mastdf):
    tries = 50
    while tries:
        try:
            start_time = time.time()
            f = h5py.File(file, 'r')
            print(f"Time taken to open file: {time.time() - start_time:.4f} seconds")
            break
        except Exception as e:
            print(f"Error opening file: {e}")
            print(f"Retry {tries}")
            tries -= 1
            time.sleep(1)

    if tries == 0:
        return

    start_data_time = time.time()
    rms = []
    start_read_time = time.time()
    data = f['data']
    print(f"Time taken to read data: {time.time() - start_read_time:.4f} seconds")
    data = data.astype(np.float32)
    # Reverse the order of data on axis=1
    data = np.flip(data, axis=1)
    print(f"Time taken to process data: {time.time() - start_data_time:.4f} seconds")

    # Use numpy's in-place multiplication for speed
    data *= f['header']['dataScale'][()]
    # For parallel processing, you could use numpy's array_split and ThreadPoolExecutor:
    # scale = f['header']['dataScale'][()]
    # chunks = np.array_split(data, os.cpu_count(), axis=0)
    # def scale_chunk(chunk):
    #     chunk *= scale
    #     return chunk
    # with ThreadPoolExecutor() as executor:
    #     data = np.concatenate(list(executor.map(scale_chunk, chunks)), axis=0)
    print(f"Time taken to process data: {time.time() - start_data_time:.4f} seconds")
    data = unwrap(data, f['header']['spatialUnwrRange'][()], axis=1)
    print(f"Time taken to process data: {time.time() - start_data_time:.4f} seconds")
    data = np.cumsum(data, axis=0) * f['header']['dt']
    print(f"Time taken to process data: {time.time() - start_data_time:.4f} seconds")
    data /= (f['header']['sensitivities'][0] / 1e9)
    print(f"Time taken to process data: {time.time() - start_data_time:.4f} seconds")
    
    start_metrics_time = time.time()
    with ThreadPoolExecutor() as executor:
        rms_future = executor.submit(get_rms, data, file)
        var_future = executor.submit(get_variance, data, file)
        rms_means_future = executor.submit(get_rms_chunks, rms_future.result(), mastdf, file)

        rms = rms_future.result()
        var = var_future.result()
        rms_means = rms_means_future.result()
    print(f"Time taken to compute metrics: {time.time() - start_metrics_time:.4f} seconds")
        
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
        print(f"Received message: {message}")
        process_data(message['dest_path'], df)

if __name__ == "__main__":
    zmq_server()