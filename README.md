Default settings:

* Input = /home/user/media/transcode_input
* Output = /home/user/media/transcode_output
* H.264 video codec (Change in config.json. More in "Configuration" section)
* 320 kbps audio bitrate

<!-- ABOUT THE SCRIPT -->
## About the Script

Simple-Transcoder is a simple and effecient way to transcode video files. It uses HandbrakeCLI under the hood to transcode video files. It is designed to be run as a schedualed task or manually. I am not a python programmer, so forgive me if this is not up to python standards.


<!-- PREREQUISITES -->
## Prerequisites

1. Install Python
```sh
sudo apt install python3
```
2. Install ffmpeg
```sh
sudo apt install ffmpeg
```
3. Add ffmpeg to your PATH, follow this guide for windows
```sh
https://phoenixnap.com/kb/ffmpeg-windows
```

<!-- INSTALLATION -->
## Installation

1. Update your packages and libraries
```sh
sudo apt update && sudo apt upgrade -y
```

2. Install the Simple-Transcoder script by running 
```sh
git clone https://github.com/oliverdougherC/Simple-Transcoder
```
3. Navigate to the Simple-Transcoder directory
```sh
cd Simple-Transcoder
```

<!-- CONFIGURATION -->
## Configuration

1. If desired, change the transcoding settings in the *config.json* file. 
```sh
nano config.json
```


<!-- USAGE -->
## Usage

1. Run the script
```sh
python3 run_transcode.py
```
The first time you run the script, the it will create the default directories specified in the *config.json* file if they do not exist.

2. Sit back and relax while the script transcodes your videos.
3. If you run into an error or are just curious, take a look at the log file
```sh
cat logs/transcoding.log
```


