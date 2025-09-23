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
import msgpack
import gzip
from watchdog.events import FileSystemEvent
import zmq
import getopt

def simulate_file_changes(src_path, hostname, port):
	"""
	Simulate file creation and modification events in the specified directory.
	"""
	context = zmq.Context()
	socket = context.socket(zmq.PUSH)
	socket.connect(f"tcp://{hostname}:{port}")

	while True:
		hdf5_files = [os.path.join(src_path, f) for f in os.listdir(src_path) if f.endswith('.hdf5')]
		for filename in hdf5_files:
			message = {'src_path': f'{src_path}/{filename}'}
			message['dest_path'] = f'{src_path}/{filename}'
			print(f'Send zmq message: {message}')
			socket.send_json(message)
			print(f'Message sent')
			time.sleep(10)

	socket.close()
	context.term()
	
class Handler(watchdog.events.PatternMatchingEventHandler):
	hostname = None
	port = None

	def __init__(self):
		watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=['*.hdf5'],
															ignore_directories=True, case_sensitive=True)

	# def on_any_event(self, event):
		# print(event)

	# def on_created(self, event):
	#     print(event.src_path)
		# Process(target=process_data, args=(f'{event.src_path}',)).start()

	#    print("Watchdog received created event - % s." % event.src_path)
	#    # Event is created, you can process it now

	# def on_modified(self, event):
	#     print("Watchdog received modified event - % s." % event.src_path)
	#    # Event is modified, you can process it now
 
	def on_moved(self, event):
		print(f"File moved from {event.src_path} to {event.dest_path}")
		context = zmq.Context()
		socket = context.socket(zmq.PUSH)
		socket.connect(f"tcp://{self.hostname}:{self.port}")

		message = {'src_path': event.src_path}
		message['dest_path'] = event.dest_path
  
		print(f'Send zmq message: {message}')
		socket.send_json(message)
		print(f'Message sent')

		socket.close()
		context.term()


if __name__ == "__main__":
	def usage():
		print("Usage: capture_remote.py -s <srcpath> -h <hostname> [-p <12345>] [--sim]")
		sys.exit(1)

	try:
		opts, args = getopt.getopt(sys.argv[1:], "s:h:p:", ["srcpath=", "hostname=", "port=", "sim"])
	except getopt.GetoptError:
		usage()

	src_path = hostname = None
	port = "12345"  # Default port

	sim = False
	for opt, arg in opts:
		if opt in ("-s", "--srcpath"):
			src_path = arg
		elif opt in ("-h", "--hostname"):
			hostname = arg
		elif opt in ("-p", "--port"):
			port = arg
		elif opt == "--sim":
			sim = True

	if not src_path or not hostname or not port:
		usage()

	if sim:
		try:
			simulate_file_changes(src_path, hostname, port)
			print("Simulation completed.")
			sys.exit(0)
		except KeyboardInterrupt:
			print("Simulation interrupted by user.")
			sys.exit(0)

	event_handler = Handler()
	observer = watchdog.observers.Observer()
	observer.schedule(event_handler, path=src_path, recursive=True)
	observer.hostname = hostname
	observer.port = port
	observer.start()
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		observer.stop()
	observer.join()
