#!/usr/bin/env python3

import zmq
import time
from multiprocessing import Process
import h5py
import numpy as np
import requests
import json
import msgpack
import gzip


def process_data(file):
	start = 0
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
	# print(f['data'].shape) 
	data = f['data']
	# print(data.shape) 
	data = data.astype(np.float32)
	rms = np.sqrt(np.mean(np.square(data), axis=0)).tolist()
	rms_split = np.array_split(rms, 8)
	rms_means = [np.mean(chunk) for chunk in rms_split]
 
	var = np.var(data, axis=0).tolist()
	print(rms[0], var[0], f['data'].shape, f['cableSpec']['sensorDistances'][1]) 

	# serialized = msgpack.packb(data.tolist())
	# compressed = gzip.compress(serialized)

	# sys.exit(0)
	start += 100
	# rmsdf = pd.DataFrame(np.array(rms), columns=['rms'])

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
	data = f['data'][:, ::1]
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

    while True:
        message = socket.recv_json()
        process_data(message['dest_path'])
        print(f"Received message: {message}")

if __name__ == "__main__":
    zmq_server()