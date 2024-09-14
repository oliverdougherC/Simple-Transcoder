import subprocess
import sys
import os
import json
import logging
import shutil
import re
import time
import threading
import queue

shutdown_flag = threading.Event()

def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, 'transcoding.log')
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    
    console_format = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def load_config():
    logger.info("Loading config")
    config_path = 'config.json'
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as config_file:
        content = config_file.read()
        if not content.strip():
            logger.error(f"Config file is empty: {config_path}")
            raise ValueError(f"Config file is empty: {config_path}")
        
        try:
            config = json.loads(content)
            config['video_codec'] = config['video_codec'].lower()
            config['video_bitrate'] = int(config.get('video_bitrate', 0))
            config['audio_bitrate'] = int(config.get('audio_bitrate', 0))
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise

def check_ffmpeg_installed():
    return shutil.which("ffmpeg") is not None

def get_video_info(file_path):
    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running ffprobe: {e}")
        return None

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

    if input_info is None or output_info is None:
        logger.error("Unable to print video comparison due to missing video information.")
        return

    input_video_stream = next(s for s in input_info['streams'] if s['codec_type'] == 'video')
    output_video_stream = next(s for s in output_info['streams'] if s['codec_type'] == 'video')

    input_audio_stream = next(s for s in input_info['streams'] if s['codec_type'] == 'audio')
    output_audio_stream = next(s for s in output_info['streams'] if s['codec_type'] == 'audio')

    input_video_bitrate = input_video_stream.get('bit_rate', 'N/A')
    output_video_bitrate = output_video_stream.get('bit_rate', 'N/A')
    input_audio_bitrate = input_audio_stream.get('bit_rate', 'N/A')
    output_audio_bitrate = output_audio_stream.get('bit_rate', 'N/A')

    logger.info("\nVideo Comparison:")
    logger.info(f"{'Property':<20} {'Input':<30} {'Output':<30}")
    logger.info("-" * 80)
    logger.info(f"{'Video Codec':<20} {input_video_stream['codec_name']:<30} {output_video_stream['codec_name']:<30}")
    logger.info(f"{'Audio Codec':<20} {input_audio_stream['codec_name']:<30} {output_audio_stream['codec_name']:<30}")
    input_res = f"{input_video_stream['width']}x{input_video_stream['height']}"
    output_res = f"{output_video_stream['width']}x{output_video_stream['height']}"
    logger.info(f"{'Resolution':<20} {input_res:<30} {output_res:<30}")
    logger.info(f"{'Video Bitrate':<20} {human_readable_bitrate(input_video_bitrate):<30} {human_readable_bitrate(output_video_bitrate):<30}")
    logger.info(f"{'Audio Bitrate':<20} {human_readable_bitrate(input_audio_bitrate):<30} {human_readable_bitrate(output_audio_bitrate):<30}")
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
    
    if input_info is None or output_info is None:
        logger.error("Unable to verify transcoding due to missing video information.")
        return False
    
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
        if shutil.which("nvidia-smi"):
            nvidia_smi = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if nvidia_smi.returncode == 0:
                return "nvidia"
        
        if shutil.which("vainfo"):
            vainfo = subprocess.run(["vainfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "Intel" in vainfo.stdout:
                return "intel"
        
        if shutil.which("rocm-smi"):
            rocm_smi = subprocess.run(["rocm-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if rocm_smi.returncode == 0:
                return "amd"
    except Exception as e:
        logger.error(f"Error detecting GPU: {e}")
    
    return "cpu"

def check_encoder_support(encoder):
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, check=True)
        return encoder in result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting encoder list: {e}")
        return False

def get_encoder(config_encoder, gpu_type):
    codec_aliases = {
        "h264": ["x264", "h.264", "avc"],
        "hevc": ["x265", "h265", "h.265"],
        "av1": []
    }

    # Normalize the config_encoder
    for codec, aliases in codec_aliases.items():
        if config_encoder.lower() in [codec] + [alias.lower() for alias in aliases]:
            config_encoder = codec
            break

    gpu_encoders = {
        "nvidia": {
            "h264": "h264_nvenc",
            "hevc": "hevc_nvenc",
            "av1": "av1_nvenc",
        },
        "intel": {
            "h264": "h264_qsv",
            "hevc": "hevc_qsv",
            "av1": "av1_qsv",
        },
        "amd": {
            "h264": "h264_amf",
            "hevc": "hevc_amf",
        }
    }

    if gpu_type in gpu_encoders and config_encoder in gpu_encoders[gpu_type]:
        gpu_encoder = gpu_encoders[gpu_type][config_encoder]
        if check_encoder_support(gpu_encoder):
            return gpu_encoder
        else:
            logger.warning(f"GPU encoder {gpu_encoder} not available. Falling back to CPU encoding.")
    
    # Fall back to CPU encoding
    if config_encoder == "h264":
        return "libx264"
    elif config_encoder == "hevc":
        return "libx265"
    elif config_encoder == "av1":
        return "libaom-av1"
    else:
        logger.warning(f"Unsupported encoder: {config_encoder}. Falling back to libx264.")
        return "libx264"

def transcode_video(input_file, output_file, config):
    logger.debug(f"Starting transcoding of {input_file}")
    if not check_ffmpeg_installed():
        logger.error("FFmpeg is not installed. Please install it and try again.")
        return False

    gpu_type = detect_gpu()
    encoder = get_encoder(config['video_codec'], gpu_type)
    logger.info(f"Transcoding to {encoder} using {gpu_type.upper()} acceleration")
    logger.debug(f"Detected GPU type: {gpu_type}")
    logger.debug(f"Using encoder: {encoder}")

    command = [
        "ffmpeg",
        "-i", input_file,
        "-map", "0",  # Include all streams from the input
        "-c:v", encoder,
    ]

    if config['video_bitrate'] > 0:
        command.extend(["-b:v", f"{config['video_bitrate']}k"])
        command.extend(["-maxrate", f"{int(config['video_bitrate'] * 1.5)}k"])
        command.extend(["-bufsize", f"{config['video_bitrate'] * 2}k"])
    else:
        # When video_bitrate is 0, use the input bitrate
        input_info = get_video_info(input_file)
        input_video_stream = next(s for s in input_info['streams'] if s['codec_type'] == 'video')
        input_bitrate = input_video_stream.get('bit_rate')
        if input_bitrate:
            command.extend(["-b:v", input_bitrate])

    # Audio settings
    command.extend(["-c:a", "copy"])  # Copy audio streams by default
    if config['audio_bitrate'] > 0:
        command.extend(["-c:a:0", "aac", "-b:a:0", f"{config['audio_bitrate']}k"])  # Re-encode only the first audio stream if bitrate is specified

    # Subtitle settings
    command.extend(["-c:s", "copy"])  # Copy subtitle streams

    command.extend([
        "-y",
        output_file
    ])

    try:
        logger.debug(f"Running command: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        duration = get_video_duration(input_file)
        start_time = time.time()
        last_update_time = start_time
        last_progress = 0
        last_frame = 0
        
        while True:
            if shutdown_flag.is_set():
                process.terminate()
                logger.info(f"Transcoding of {os.path.basename(input_file)} interrupted due to shutdown request.")
                return False

            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logger.debug(f"FFmpeg output: {output.strip()}")
                progress = parse_progress(output, duration)
                if progress:
                    current_time = time.time()
                    elapsed_time = current_time - start_time
                    if current_time - last_update_time >= 1:  # Update every second
                        progress_diff = progress['percentage'] - last_progress
                        time_diff = current_time - last_update_time
                        frame_diff = progress['frame'] - last_frame
                        
                        # Calculate speed as percentage per second
                        speed = progress_diff / time_diff if time_diff > 0 else 0
                        
                        # Calculate FPS
                        fps = frame_diff / time_diff if time_diff > 0 else 0
                        
                        # Calculate overall FPS
                        overall_fps = progress['frame'] / elapsed_time if elapsed_time > 0 else 0
                        
                        # Estimate ETA based on remaining percentage and current speed
                        remaining_percentage = 100 - progress['percentage']
                        eta = remaining_percentage / speed if speed > 0 else 0
                        
                        print(f"\rProgress: {progress['percentage']:.2f}% | FPS: {overall_fps:.2f} | "
                              f"Speed: {speed:.2f}%/s | ETA: {eta:.2f}s", end='')
                        sys.stdout.flush()
                        last_update_time = current_time
                        last_progress = progress['percentage']
                        last_frame = progress['frame']

        print()  # New line after progress
        
        if process.returncode != 0:
            logger.error(f"FFmpeg process returned non-zero exit code: {process.returncode}")
            return False

        logger.info(f"Transcoding complete: {os.path.basename(input_file)}")
        
        if verify_transcoding(input_file, output_file):
            print_video_comparison(input_file, output_file)
            return True
        else:
            logger.error("Transcoding verification failed. Please check the output file.")
            return False
    except Exception as e:
        logger.error(f"Error during transcoding: {e}")
        return False

def get_video_duration(file_path):
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return float(result.stdout)

def parse_progress(output, duration):
    time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", output)
    frame_match = re.search(r"frame=\s*(\d+)", output)
    if time_match and frame_match:
        hours, minutes, seconds = map(float, time_match.groups())
        time = hours * 3600 + minutes * 60 + seconds
        frame = int(frame_match.group(1))
        percentage = (time / duration) * 100 if duration > 0 else 0
        return {'time': time, 'frame': frame, 'percentage': percentage}
    return None

def process_directory(config):
    input_dir = os.path.expanduser(config['input_directory'])
    output_dir = os.path.expanduser(config['output_directory'])
    extensions = config['file_extensions']

    if not os.path.exists(input_dir):
        os.makedirs(input_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files_to_process = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if any(file.lower().endswith(ext.lower()) for ext in extensions):
                input_path = os.path.join(root, file)
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path)
                files_to_process.append((input_path, output_path))

    total_files = len(files_to_process)
    logger.info(f"Found {total_files} files to process")

    failed_files = []

    for index, (input_path, output_path) in enumerate(files_to_process, start=1):
        if shutdown_flag.is_set():
            logger.info("Graceful shutdown initiated. Stopping further processing.")
            break

        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        file_name = os.path.basename(input_path)
        logger.info(f"Transcoding [{index}/{total_files}]: {file_name}")
        
        success = transcode_video(input_path, output_path, config)
        if not success:
            logger.warning(f"Transcoding failed for {file_name}")
            failed_files.append(file_name)

    if shutdown_flag.is_set():
        logger.info("Processing stopped due to user request.")
    elif not failed_files:
        logger.info("All files successfully transcoded.")
    else:
        logger.info("Transcoding process completed. Some files encountered errors.")
        logger.info("Failed files:")
        for failed_file in failed_files:
            logger.info(f"- {failed_file}")

    return failed_files

def listen_for_quit():
    global shutdown_flag
    while not shutdown_flag.is_set():
        if input().lower() == 'q':
            print("\nGraceful shutdown initiated. Completing current file...")
            shutdown_flag.set()
            break

if __name__ == "__main__":
    logger = setup_logging()
    logger.info("Transcoding script started")

    gpu_type = detect_gpu()
    if gpu_type != "cpu":
        logger.info(f"GPU acceleration ({gpu_type}) will be used when possible")
    else:
        logger.info("No compatible GPU detected, using CPU encoding")

    print("Enter 'q' at any time to gracefully stop the process.")

    input_thread = threading.Thread(target=listen_for_quit)
    input_thread.daemon = True
    input_thread.start()

    try:
        config = load_config()
        logger.debug("Config loaded successfully")
        failed_files = process_directory(config)
    except Exception as e:
        logger.exception("An unexpected error occurred:")
    finally:
        shutdown_flag.set()  # Ensure the input thread stops
        input_thread.join(timeout=1)  # Wait for the input thread to finish
        if shutdown_flag.is_set():
            logger.info("Script execution interrupted by user.")
        elif not failed_files:
            logger.info("Script execution completed. All files successfully transcoded.")
        else:
            logger.info("Script execution completed. Some files encountered errors:")
            for failed_file in failed_files:
                logger.info(f"- {failed_file}")
