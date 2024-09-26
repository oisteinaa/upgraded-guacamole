#! /usr/bin/env python3

import os
import shutil
import sys
import time

def copy_files_with_extension(src_dir, dest_dir, extension):
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    
    for filename in os.listdir(src_dir):
        if filename.endswith(extension):
            src_file = os.path.join(src_dir, filename)
            dest_file = os.path.join(dest_dir, filename)
            shutil.copy2(src_file, dest_file)
            print(f"Copied {src_file} to {dest_file}")
            time.sleep(10)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python interrogator_sim.py <source_directory> <destination_directory>")
        sys.exit(1)
    
    source_directory = sys.argv[1]
    destination_directory = sys.argv[2]
    extension = ".hdf5"
    
    copy_files_with_extension(source_directory, destination_directory, extension)