#! /usr/bin/env python

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from sensnetlib.dbfunc import get_event_limits, insert_event

def event_detected(evrow, data):
    """
    Placeholder function to handle detected events.
    """
    print(f"Event detected: {evrow['data_type']}, {data}, {evrow['name']}")
    insert_event(evrow['data_type'], data, evrow['name'])
    

def detect_events(data):
    limitdf = get_event_limits()
    
    for i, (index, evrow) in enumerate(limitdf.iterrows()):
        if evrow['absolute']:
            value = abs(data[i])
        else:
            value = data[i]
        
        if value > evrow['limit']:
            event_detected(evrow, value)
            

if __name__ == "__main__":
    pass