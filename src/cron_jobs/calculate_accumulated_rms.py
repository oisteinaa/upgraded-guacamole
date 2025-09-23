#! /usr/bin/env python3

import os
import json
import datetime

def process_data():
    def get_rms_files(directories, start_time, end_time):
        rms_files = []
        for directory in directories:
            if not os.path.exists(directory):
                continue
            for fname in os.listdir(directory):
                if fname.endswith('.json'):
                    try:
                        rms_files.append(os.path.join(directory, fname))
                    except Exception:
                        continue
        print(f"Found {len(rms_files)} RMS files between {start_time} and {end_time}")
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

    def get_directories_between(start_time, end_time):
        directories = []
        current = start_time
        while current <= end_time:
            year = current.year
            month = f"{current.month:02d}"
            day = f"{current.day:02d}"
            dir_path = f"/raid1/sensnet_data/rms/{year}/{month}/{day}/"
            directories.append(dir_path)
            current += datetime.timedelta(days=1)
        return directories

    now = datetime.datetime.now()
    results = {}
    for weeks in [1, 2, 4]:
        start_time = now - datetime.timedelta(weeks=weeks)
        directories = get_directories_between(start_time, now)
        rms_files = get_rms_files(directories, start_time, now)
        avg_rms = calculate_average_rms(rms_files)
        results[f"{weeks}_weeks"] = avg_rms

    output_path = f"/raid1/sensnet_data/rms/averages/average_rms.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    process_data()
