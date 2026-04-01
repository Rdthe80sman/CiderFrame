#!/usr/bin/env python3
"""
Download a small GIF and extract frames as BINs scaled to given size.
Saves output to debug/gif_test_output/
"""
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageSequence
except Exception:
    print('Pillow not installed. Please run: python -m pip install --user Pillow')
    sys.exit(2)

try:
    import cv2
except Exception:
    print('OpenCV not installed. Please run: python -m pip install --user opencv-python')
    sys.exit(2)

import urllib.request
from urllib.request import Request

import tkinter as tk
from tkinter import simpledialog
import tkinter.messagebox as messagebox
import subprocess
import shutil
import tempfile

WORK = Path(__file__).resolve().parent.parent
OUT = WORK / 'debug' / 'gif_test_output'
OUT.mkdir(parents=True, exist_ok=True)

if len(sys.argv) != 2:
    print('Usage: python extract_gif_frames.py <image_or_video_file>')
    print('Supported formats: GIF, MP4, AVI, MOV, MKV, WebM, FLV, etc.')
    sys.exit(1)

INPUT_PATH = Path(sys.argv[1])
if not INPUT_PATH.exists():
    print('File not found:', INPUT_PATH)
    sys.exit(1)

# Detect file type
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mts', '.m2ts'}
SUPPORTED_IMAGE_FORMATS = {'.gif', '.png', '.jpg', '.jpeg', '.bmp'}
FILE_EXT = INPUT_PATH.suffix.lower()

if FILE_EXT not in SUPPORTED_VIDEO_FORMATS and FILE_EXT not in SUPPORTED_IMAGE_FORMATS:
    print(f'Unsupported file format: {FILE_EXT}')
    print(f'Supported video formats: {", ".join(SUPPORTED_VIDEO_FORMATS)}')
    print(f'Supported image formats: {", ".join(SUPPORTED_IMAGE_FORMATS)}')
    sys.exit(1)

IS_VIDEO = FILE_EXT in SUPPORTED_VIDEO_FORMATS

# desired scale: try to read buckshot settings file? fallback to 140x192
# Use the Buckshot default used in UI for HGR: 140x192
width, height = 140, 192

# Get ProDOS options
root = tk.Tk()
root.withdraw()
prodos_name = simpledialog.askstring("ProDOS Name", "Enter ProDOS base name (max 15 chars):", initialvalue="FRAME")
if prodos_name:
    prodos_name = prodos_name[:15].upper()
else:
    prodos_name = "FRAME"
auxtype = simpledialog.askstring("Auxtype", "Enter auxtype (hex, e.g. 2000):", initialvalue="2000")
if not auxtype:
    auxtype = "2000"

# Prompt for ProDOS image file
prodos_image_str = simpledialog.askstring("ProDOS Image", "Enter ProDOS image file path (.po/.hdv/.2mg):", initialvalue=str(OUT / f'{prodos_name}.po'))
if not prodos_image_str:
    sys.exit(1)
prodos_image = Path(prodos_image_str)

image_size = "32MB"  # default as per user request
if not prodos_image.exists():
    size_input = simpledialog.askstring("Image Size", "Select size for new ProDOS image (140KB, 800KB, 32MB):", initialvalue="32MB")
    if size_input in ["140KB", "800KB", "32MB"]:
        image_size = size_input
    else:
        image_size = "32MB"

cadius_path = Path(__file__).parent.parent / 'cadius'
if os.name == 'nt' and not cadius_path.exists():
    cadius_path = Path(__file__).parent.parent / 'cadius.exe'
if not cadius_path.exists():
    print('cadius executable not found at', cadius_path)
    sys.exit(1)

# Create volume if needed
if not prodos_image.exists():
    print(f'Creating {image_size} ProDOS volume at', prodos_image)
    result = subprocess.run([str(cadius_path), 'CREATEVOLUME', str(prodos_image), prodos_name[:15], image_size], capture_output=True, text=True)
    if result.returncode != 0:
        print('Failed to create ProDOS volume:', result.stderr)
        sys.exit(1)

# Catalog to get volume name
result = subprocess.run([str(cadius_path), 'CATALOG', str(prodos_image)], capture_output=True, text=True)
if result.returncode != 0:
    print('Failed to catalog ProDOS volume:', result.stderr)
    sys.exit(1)

import re
vol_match = re.search(r'\n(/[^/]{1,15}/)\r?\n', result.stdout)
if vol_match:
    volume_name = vol_match.group(1)
else:
    volume_name = f'/{prodos_name[:15]}/'

print('ProDOS volume name:', volume_name)

# Assume HGR format
output_format = "H"
b2d_path = Path(__file__).parent.parent / 'b2d'
if os.name == 'nt' and not b2d_path.exists():
    b2d_path = Path(__file__).parent.parent / 'b2d.exe'
if not b2d_path.exists():
    print('b2d executable not found at', b2d_path)
    sys.exit(1)

tmp_dir = tempfile.mkdtemp()

print('Extracting frames and adding to ProDOS image', prodos_image)

if IS_VIDEO:
    # Extract frames from video using OpenCV
    cap = cv2.VideoCapture(str(INPUT_PATH))
    if not cap.isOpened():
        print('Failed to open video file:', INPUT_PATH)
        sys.exit(1)
    
    i = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Convert BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Convert to PIL Image
        pil_image = Image.fromarray(frame)
        # Resize while keeping aspect ratio
        pil_image = pil_image.resize((width, height), Image.LANCZOS)
        bmp_path = Path(tmp_dir) / f'frame_{i:04d}.bmp'
        pil_image.save(bmp_path, format='BMP')
        
        # Call b2d
        result = subprocess.run([str(b2d_path), str(bmp_path), output_format], cwd=tmp_dir, capture_output=True, text=True)
        if result.returncode != 0:
            print('b2d failed for frame', i, result.stderr)
            i += 1
            continue
        
        # The output is SAVEDCH.BIN for HGR
        bin_file = Path(tmp_dir) / 'FRM.BIN'
        if bin_file.exists():
            final_bin = OUT / f'{prodos_name}_{i:04d}.BIN'
            shutil.copy(bin_file, final_bin)
            print('Wrote', final_bin.name)
            
            # Prepare for ProDOS
            prodos_file_name = f'{prodos_name}_{i:04d}.BIN'
            temp_file = Path(tmp_dir) / prodos_file_name
            shutil.copy(final_bin, temp_file)
            
            # Create _FileInformation.txt
            fileinfo_text = f'{prodos_file_name}=Type(06),AuxType({auxtype}),VersionCreate(70),MinVersion(BE),Access(E3),FolderInfo1(000000000000000000000000000000000000),FolderInfo2(000000000000000000000000000000000000)'
            fileinfo_file = Path(tmp_dir) / '_FileInformation.txt'
            with open(fileinfo_file, 'w') as f:
                f.write(fileinfo_text + '\n')
            
            # ADDFILE
            result = subprocess.run([str(cadius_path), 'ADDFILE', str(prodos_image), volume_name, str(temp_file)], capture_output=True, text=True)
            if result.returncode != 0:
                addfile_output = result.stdout + result.stderr
                if "A file already exist" in addfile_output:
                    if messagebox.askyesno("File exists in image", f"File {prodos_file_name} exists, Replace?"):
                        # DELETEFILE
                        delete_result = subprocess.run([str(cadius_path), 'DELETEFILE', str(prodos_image), f'{volume_name}{prodos_file_name}'], capture_output=True, text=True)
                        if delete_result.returncode == 0:
                            # ADDFILE again
                            result = subprocess.run([str(cadius_path), 'ADDFILE', str(prodos_image), volume_name, str(temp_file)], capture_output=True, text=True)
                            if result.returncode == 0:
                                print(f'Replaced {prodos_file_name} in ProDOS image')
                            else:
                                print(f'Failed to replace {prodos_file_name}:', result.stderr)
                        else:
                            print(f'Failed to delete {prodos_file_name}:', delete_result.stderr)
                    else:
                        print(f'Skipped {prodos_file_name}')
                else:
                    print(f'Failed to add {prodos_file_name} to ProDOS image:', result.stderr)
            else:
                print(f'Added {prodos_file_name} to ProDOS image')
        else:
            print('BIN file not found for frame', i)
        
        i += 1
    
    cap.release()
else:
    # Extract frames from GIF using PIL
    with Image.open(INPUT_PATH) as im:
        for i, frame in enumerate(ImageSequence.Iterator(im)):
            frame = frame.convert('RGBA')
            # scale while keeping aspect ratio
            frame = frame.resize((width, height), Image.LANCZOS)
            bmp_path = Path(tmp_dir) / f'frame_{i:04d}.bmp'
            frame.save(bmp_path, format='BMP')
            
            # Call b2d
            result = subprocess.run([str(b2d_path), str(bmp_path), output_format], cwd=tmp_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print('b2d failed for frame', i, result.stderr)
                continue
            
            # The output is SAVEDCH.BIN for HGR
            bin_file = Path(tmp_dir) / 'FRM.BIN'
            if bin_file.exists():
                final_bin = OUT / f'{prodos_name}_{i:04d}.BIN'
                shutil.copy(bin_file, final_bin)
                print('Wrote', final_bin.name)
                
                # Prepare for ProDOS
                prodos_file_name = f'{prodos_name}_{i:04d}.BIN'
                temp_file = Path(tmp_dir) / prodos_file_name
                shutil.copy(final_bin, temp_file)
                
                # Create _FileInformation.txt
                fileinfo_text = f'{prodos_file_name}=Type(06),AuxType({auxtype}),VersionCreate(70),MinVersion(BE),Access(E3),FolderInfo1(000000000000000000000000000000000000),FolderInfo2(000000000000000000000000000000000000)'
                fileinfo_file = Path(tmp_dir) / '_FileInformation.txt'
                with open(fileinfo_file, 'w') as f:
                    f.write(fileinfo_text + '\n')
                
                # ADDFILE
                result = subprocess.run([str(cadius_path), 'ADDFILE', str(prodos_image), volume_name, str(temp_file)], capture_output=True, text=True)
                if result.returncode != 0:
                    addfile_output = result.stdout + result.stderr
                    if "A file already exist" in addfile_output:
                        if messagebox.askyesno("File exists in image", f"File {prodos_file_name} exists, Replace?"):
                            # DELETEFILE
                            delete_result = subprocess.run([str(cadius_path), 'DELETEFILE', str(prodos_image), f'{volume_name}{prodos_file_name}'], capture_output=True, text=True)
                            if delete_result.returncode == 0:
                                # ADDFILE again
                                result = subprocess.run([str(cadius_path), 'ADDFILE', str(prodos_image), volume_name, str(temp_file)], capture_output=True, text=True)
                                if result.returncode == 0:
                                    print(f'Replaced {prodos_file_name} in ProDOS image')
                                else:
                                    print(f'Failed to replace {prodos_file_name}:', result.stderr)
                            else:
                                print(f'Failed to delete {prodos_file_name}:', delete_result.stderr)
                        else:
                            print(f'Skipped {prodos_file_name}')
                    else:
                        print(f'Failed to add {prodos_file_name} to ProDOS image:', result.stderr)
                else:
                    print(f'Added {prodos_file_name} to ProDOS image')
            else:
                print('BIN file not found for frame', i)

print('Done. ProDOS image:', prodos_image)
print('Files in:', OUT)
for f in sorted(OUT.iterdir()):
    print(' -', f.name)
