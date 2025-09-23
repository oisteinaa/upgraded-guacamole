#! /usr/bin/env python3

import os
import json
import datetime

def process_data():
    def get_rms_files(directory, start_time, end_time):
        rms_files = []
        if not os.path.exists(directory):
            return rms_files
        for fname in os.listdir(directory):
            if fname.endswith('.json'):
                try:
                    # Assuming filename format: rms_YYYYMMDD_HHMMSS.json
                    parts = fname.split('_')
                    if len(parts) < 3:
                        continue
                    dt_str = parts[1] + parts[2].replace('.json', '')
                    file_time = datetime.datetime.strptime(dt_str, "%Y%m%d%H%M%S")
                    if start_time <= file_time <= end_time:
                        rms_files.append(os.path.join(directory, fname))
                except Exception:
                    continue
        return rms_files

    def calculate_average_rms(rms_files):
        rms_values = []
        for fpath in rms_files:
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                    rms = data.get('rms')
                    if rms is not None:
                        rms_values.append(rms)
            except Exception:
                continue
        if rms_values:
            return sum(rms_values) / len(rms_values)
        return None

    now = datetime.datetime.now()
    year = now.year
    month = f"{now.month:02d}"
    day = f"{now.day:02d}"
    directory = f"/raid1/sensnet_data/rms/{year}/{month}/{day}/"
    results = {}
    for weeks in [1, 2, 4]:
        start_time = now - datetime.timedelta(weeks=weeks)
        rms_files = get_rms_files(directory, start_time, now)
        avg_rms = calculate_average_rms(rms_files)
        results[f"{weeks}_weeks"] = avg_rms

    # Store results in a file
    output_path = f"/raid1/sensnet_data/rms/averages/average_rms.json"
    
    if not os.path.exists(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    process_data()