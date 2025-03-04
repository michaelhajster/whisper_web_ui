# Whisper Web UI

This project provides both a Streamlit web application (`whisper_webui.py`) and a command-line interface (`whisper_cli.py`) for transcribing audio and video files using the Whisper model via the OpenAI API, Groq API, or Fal API. It offers a user-friendly interface for uploading media, processing it, and obtaining transcriptions quickly and efficiently.

![Screenshot_003781](https://github.com/piercecohen1/whisper-webui/assets/19575201/b1eedffc-1cdb-4671-bfcb-156d770d68ea)

## Features

- Automatic compression for files larger than 25MB
- Support for multiple audio formats (mp3, mp4, mpeg, mpga, m4a, wav, webm)
- Support for video files (mp4, avi, mov, mkv, flv, wmv) with automatic audio extraction
- Transcription using Whisper models through OpenAI, Groq, or Fal API
- Display of transcription time and results
- Option to copy transcript to clipboard
- Ability to save transcript to a file
- Both web-based and command-line interfaces

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/whisper-webui.git
   cd whisper-webui
   ```

2. Create and activate a virtual environment (recommended):
   ```
   # For Mac/Linux
   python -m venv venv
   source venv/bin/activate
   
   # For Windows
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Install ffmpeg (required for audio processing):
   - **Mac**: `brew install ffmpeg`
   - **Ubuntu/Debian**: `sudo apt update && sudo apt install ffmpeg`
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or install using Chocolatey: `choco install ffmpeg`

## Usage

### Streamlit Web Application (`whisper_webui.py`)

1. Run the Streamlit app:
   ```
   streamlit run whisper_webui.py
   ```

2. Open your web browser and navigate to the provided local URL (typically `http://localhost:8501`).

3. In the app, expand the "API Settings" section and enter your OpenAI API key.
   - You can get an API key from the [OpenAI platform](https://platform.openai.com/api-keys).
   - Optionally, you can also enter Groq or Fal API keys to use those services.

4. Upload an audio or video file, select the API to use, and click "Transcribe Media" to transcribe it.

5. Once transcription is complete, you can view the result, copy it to clipboard, or save it to a file.

### Setting API Keys as Environment Variables (Optional)

You can set API keys as environment variables to avoid entering them each time:

```
# For Mac/Linux
export OPENAI_API_KEY='your_openai_api_key_here'
export GROQ_API_KEY='your_groq_api_key_here'
export FAL_KEY='your_fal_api_key_here'

# For Windows
set OPENAI_API_KEY=your_openai_api_key_here
set GROQ_API_KEY=your_groq_api_key_here
set FAL_KEY=your_fal_api_key_here
```

### Command-Line Interface (`whisper_cli.py`)

The CLI version offers more flexibility and options for transcription. Here's how to use it:

```
python whisper_cli.py [-h] input_file [-o OUTPUT] [-c] [--compress-only] [--api {openai,groq}]
```

Options:
- `input_file`: Path to the audio or video file to transcribe (required)
- `-o OUTPUT`, `--output OUTPUT`: Output file for the transcript (default: input_file_transcript.txt)
- `-c`, `--copy`: Copy transcript to clipboard
- `--compress-only`: Only compress the audio file, do not transcribe
- `--api {openai,groq}`: API to use for transcription (default: openai)

Examples:

1. Transcribe an audio file using OpenAI API:
   ```
   python whisper_cli.py my_audio.mp3
   ```

2. Transcribe a video file using Groq API and copy to clipboard:
   ```
   python whisper_cli.py my_video.mp4 -c --api groq
   ```

3. Transcribe an audio file and save to a specific output file:
   ```
   python whisper_cli.py my_audio.wav -o my_transcript.txt
   ```

## Note on Fal API Usage

If using the Fal.ai API for transcription, the application uploads your audio file to tmpfiles.org. This step is necessary because the Fal API requires input files to be accessible via a public URL.

Please ensure that you have the necessary rights to upload and make your audio public. Do not use this method for sensitive recordings.

## Troubleshooting

- **"ffmpeg is not installed or not in PATH"**: The application requires ffmpeg for audio processing. Follow the installation instructions in the app or in the Installation section above.
- **"OpenAI API key is not set"**: Make sure to enter your OpenAI API key in the "API Settings" section or set it as an environment variable.
- **"Client.init() got an unexpected keyword argument 'proxies'"**: This error occurs when proxy settings in your environment are causing conflicts with the API clients.
  
  To fix this issue, try one of these solutions:
  
  1. Run the application without proxy environment variables:
     ```
     # For Mac/Linux
     env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy streamlit run whisper_webui.py
     
     # For Windows
     set HTTP_PROXY=
     set HTTPS_PROXY=
     streamlit run whisper_webui.py
     ```
  
  2. If you're behind a corporate proxy, you may need to configure your proxy settings explicitly for Python packages. 
     Create a `.env` file with your proxy settings and use those instead of environment variables.

- **File size errors**: Files larger than 25MB will be automatically compressed to fit within OpenAI's size limits.

## License

This project is released under the [MIT License](LICENSE).
