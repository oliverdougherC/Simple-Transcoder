import subprocess
import sys
import os
import json
import logging
import shutil
import re

def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, 'transcoding.log')
    
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Create handlers
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create formatters and add it to handlers
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    
    console_format = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_format)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def load_config():
    logger.info("Loading config")
    config_path = 'config.json'  # Adjust this if your config file has a different name or path
    
    logger.info(f"Checking if config file exists: {config_path}")
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    logger.info("Reading config file")
    with open(config_path, 'r') as config_file:
        content = config_file.read()
        if not content.strip():
            logger.error(f"Config file is empty: {config_path}")
            raise ValueError(f"Config file is empty: {config_path}")
        
        logger.info("Parsing JSON")
        try:
            config = json.loads(content)
            # Ensure video_codec is lowercase
            config['video_codec'] = config['video_codec'].lower()
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            logger.error(f"Content of {config_path}:")
            logger.error(content)
            raise

def check_handbrake_installed():
    try:
        subprocess.run(["HandBrakeCLI", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def get_video_info(file_path):
    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return json.loads(result.stdout)

def human_readable_size(size_in_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

def human_readable_bitrate(bitrate):
    if bitrate is None or bitrate == 'N/A':
        return 'N/A'
    bitrate = float(bitrate)
    for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
        if bitrate < 1000.0:
            return f"{bitrate:.2f} {unit}"
        bitrate /= 1000.0
    return f"{bitrate:.2f} Tbps"

def print_video_comparison(input_file, output_file):
    input_info = get_video_info(input_file)
    output_info = get_video_info(output_file)

    input_video_stream = next(s for s in input_info['streams'] if s['codec_type'] == 'video')
    output_video_stream = next(s for s in output_info['streams'] if s['codec_type'] == 'video')

    input_audio_stream = next(s for s in input_info['streams'] if s['codec_type'] == 'audio')
    output_audio_stream = next(s for s in output_info['streams'] if s['codec_type'] == 'audio')

    input_bitrate = input_info['format'].get('bit_rate', 'N/A')
    output_bitrate = output_info['format'].get('bit_rate', 'N/A')

    logger.info("\nVideo Comparison:")
    logger.info(f"{'Property':<20} {'Input':<30} {'Output':<30}")
    logger.info("-" * 80)
    logger.info(f"{'Video Codec':<20} {input_video_stream['codec_name']:<30} {output_video_stream['codec_name']:<30}")
    logger.info(f"{'Audio Codec':<20} {input_audio_stream['codec_name']:<30} {output_audio_stream['codec_name']:<30}")
    input_res = f"{input_video_stream['width']}x{input_video_stream['height']}"
    output_res = f"{output_video_stream['width']}x{output_video_stream['height']}"
    logger.info(f"{'Resolution':<20} {input_res:<30} {output_res:<30}")
    logger.info(f"{'Bitrate':<20} {human_readable_bitrate(input_bitrate):<30} {human_readable_bitrate(output_bitrate):<30}")
    logger.info(f"{'Duration':<20} {input_info['format']['duration']:<30} {output_info['format']['duration']:<30}")
    logger.info(f"{'File Size':<20} {human_readable_size(os.path.getsize(input_file)):<30} {human_readable_size(os.path.getsize(output_file)):<30}")

def verify_transcoding(input_file, output_file, tolerance=1.0):
    logger.info("Verifying transcoding...")
    
    if not os.path.exists(output_file):
        logger.error(f"Error: Output file does not exist: {output_file}")
        return False
    
    if os.path.getsize(output_file) == 0:
        logger.error(f"Error: Output file is empty: {output_file}")
        return False
    
    input_info = get_video_info(input_file)
    output_info = get_video_info(output_file)
    
    input_duration = float(input_info['format']['duration'])
    output_duration = float(output_info['format']['duration'])
    
    duration_diff = abs(input_duration - output_duration)
    
    if duration_diff > tolerance:
        logger.error(f"Error: Duration mismatch. Input: {input_duration:.2f}s, Output: {output_duration:.2f}s")
        return False
    
    logger.info("Verification passed: Output file exists, is non-empty, and has correct duration.")
    return True

def detect_gpu():
    try:
        # Check for NVIDIA GPU
        if shutil.which("nvidia-smi"):
            nvidia_smi = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if nvidia_smi.returncode == 0:
                return "nvidia"
        
        # Check for Intel GPU (on Linux)
        if shutil.which("vainfo"):
            vainfo = subprocess.run(["vainfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "Intel" in vainfo.stdout:
                return "intel"
        
        # Check for AMD GPU (on Linux)
        if shutil.which("rocm-smi"):
            rocm_smi = subprocess.run(["rocm-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if rocm_smi.returncode == 0:
                return "amd"
    except Exception as e:
        logger.error(f"Error detecting GPU: {e}")
    
    return "cpu"

def get_encoder(config_encoder, gpu_type):
    gpu_encoders = {
        "nvidia": {
            "h264": "nvenc_h264",
            "x264": "nvenc_h264",
            "hevc": "nvenc_h265",
            "x265": "nvenc_h265",
            "av1": "nvenc_av1",
        },
        "intel": {
            "h264": "qsv_h264",
            "x264": "qsv_h264",
            "hevc": "qsv_h265",
            "x265": "qsv_h265",
            "av1": "qsv_av1",
        },
        "amd": {
            "h264": "vce_h264",
            "x264": "vce_h264",
            "hevc": "vce_h265",
            "x265": "vce_h265",
        }
    }

    if gpu_type in gpu_encoders and config_encoder in gpu_encoders[gpu_type]:
        return gpu_encoders[gpu_type][config_encoder]
    return config_encoder

def handle_handbrake_output(process, current_file, total_files, input_file):
    progress_pattern = re.compile(r'Encoding: task \d+ of \d+, (\d+\.\d+) %.*?(\d+\.\d+) fps, avg (\d+\.\d+) fps, ETA (\d+h\d+m\d+s)')
    for line in process.stdout:
        match = progress_pattern.search(line)
        if match:
            progress, current_fps, avg_fps, eta = match.groups()
            sys.stdout.write(f"\r[{current_file}/{total_files}] {os.path.basename(input_file)} - Progress: {progress}% | FPS: {current_fps} | ETA: {eta}")
            sys.stdout.flush()
        logger.debug(line.strip())
    sys.stdout.write("\n")
    sys.stdout.flush()

def transcode_video(input_file, output_file, config, current_file, total_files):
    logger.debug(f"Starting transcoding of {input_file}")
    if not check_handbrake_installed():
        logger.error("HandBrakeCLI is not installed. Please install it and try again.")
        sys.exit(1)

    gpu_type = detect_gpu()
    encoder = get_encoder(config['video_codec'], gpu_type)
    logger.debug(f"Detected GPU type: {gpu_type}")
    logger.debug(f"Using encoder: {encoder}")

    # Check if the encoder is supported
    supported_encoders = ["x264", "x265", "nvenc_h264", "nvenc_h265", "qsv_h264", "qsv_h265", "vce_h264", "vce_h265"]
    if encoder not in supported_encoders:
        logger.error(f"Unsupported encoder: {encoder}. Falling back to x264.")
        encoder = "x264"

    command = [
        "HandBrakeCLI",
        "-i", input_file,
        "-o", output_file,
        "-e", encoder,
        "-q", str(config['quality']),
        "-B", str(config['audio_bitrate']),
        "-t", "100%"
    ]

    # Add GPU-specific options
    if gpu_type == "nvidia":
        command.extend([
            "--encoder-preset", "slow",
            "--encoder-profile", "high",
            "--encoder-level", "auto"
        ])
    elif gpu_type == "intel":
        command.extend([
            "--encoder-preset", "balanced",
            "--encoder-profile", "main",
            "--encoder-level", "auto"
        ])
    elif gpu_type == "amd":
        command.extend([
            "--encoder-preset", "slow",
            "--encoder-profile", "main",
            "--encoder-level", "auto"
        ])

    try:
        logger.debug(f"Running command: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        handle_handbrake_output(process, current_file, total_files, input_file)
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        logger.info(f"Transcoding complete: {os.path.basename(input_file)}")
        
        if verify_transcoding(input_file, output_file):
            print_video_comparison(input_file, output_file)
        else:
            logger.error("Transcoding verification failed. Please check the output file.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during transcoding: {e}")
        sys.exit(1)

def process_directory(config):
    logger.debug("Processing directory")
    
    input_dir = os.path.expanduser(config['input_directory'])
    output_dir = os.path.expanduser(config['output_directory'])
    extensions = config['file_extensions']

    logger.debug(f"Input directory: {input_dir}")
    logger.debug(f"Output directory: {output_dir}")
    logger.debug(f"File extensions to process: {extensions}")

    # Create input and output directories if they don't exist
    for dir_path in [input_dir, output_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logger.info(f"Created directory: {dir_path}")

    # Get total number of files to process
    total_files = sum(len(files) for _, _, files in os.walk(input_dir) 
                      if any(f.lower().endswith(ext) for f in files for ext in extensions))
    
    current_file = 0

    # Walk through all subdirectories
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                current_file += 1
                input_file = os.path.join(root, file)
                
                # Create relative path
                rel_path = os.path.relpath(root, input_dir)
                
                # Create corresponding output directory
                output_subdir = os.path.join(output_dir, rel_path)
                if not os.path.exists(output_subdir):
                    os.makedirs(output_subdir)
                
                # Create output file path with the same name as input
                output_file = os.path.join(output_subdir, file)
                
                # Call transcode function
                transcode_video(input_file, output_file, config, current_file, total_files)

    logger.info("Finished processing all directories and files")

if __name__ == "__main__":
    logger = setup_logging()
    logger.info("Transcoding script started")

    gpu_type = detect_gpu()
    if gpu_type != "cpu":
        logger.info(f"GPU acceleration ({gpu_type}) will be used when possible")
    else:
        logger.info("No compatible GPU detected, using CPU encoding")

    try:
        config = load_config()
        logger.debug("Config loaded successfully")
        process_directory(config)
    except Exception as e:
        logger.exception("An error occurred:")
        sys.exit(1)

    logger.info("Transcoding script completed")
