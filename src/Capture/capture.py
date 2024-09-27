#! /usr/bin/env python3

import watchdog.events
import watchdog.observers
import time
from multiprocessing import Process
import h5py
import pandas as pd
import numpy as np
import requests
import os
import sys
import json
from watchdog.events import FileSystemEvent



def process_data(file):
	start = 0
	url = 'http://127.0.0.1:5000/rms'
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
	data = f['data'][:]
	data = data.astype(np.float32)
	rms = np.sqrt(np.mean(np.square(data), axis=0)).tolist()
	var = np.sqrt(np.max(data, axis=0)).tolist()
	print(rms[0], var[0], f['data'].shape) 

	# sys.exit(0)
	start += 100
	# rmsdf = pd.DataFrame(np.array(rms), columns=['rms'])

	rms_json = {'rms': rms, 'var': var}
	headers = {
		'Content-type': 'application/json',
		'Accept': 'application/json'
	}
	requests.post(url, json=json.dumps(rms_json), headers=headers)

class Handler(watchdog.events.PatternMatchingEventHandler):
	def __init__(self):
		# Set the patterns for PatternMatchingEventHandler
		watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=['*.hdf5'],
															ignore_directories=True, case_sensitive=True)

	# def on_any_event(self, event):
	#	print(os.stat(event.src_path), event)

	def on_created(self, event):
		print(event.src_path)
		Process(target=process_data, args=(f'{event.src_path}',)).start()

	#	print("Watchdog received created event - % s." % event.src_path)
	#	# Event is created, you can process it now

	# def on_modified(self, event):
	#	print("Watchdog received modified event - % s." % event.src_path)
	#	# Event is modified, you can process it now

	# def on_closed(self, event):
	#	print("Watchdog received closed event - % s." % event.src_path)
	#	# Event is modified, you can process it now


if __name__ == "__main__":
	# process_data(sys.argv[1])
	src_path = sys.argv[1]
	event_handler = Handler()
	observer = watchdog.observers.Observer()
	observer.schedule(event_handler, path=src_path, recursive=True)
	observer.start()
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		observer.stop()
	observer.join()
