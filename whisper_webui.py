import streamlit as st
import os
import time
import subprocess
import tempfile
import pyperclip
import requests
import json
import shutil
import base64
from datetime import datetime
from groq import Groq
from openai import OpenAI  # Updated import

def is_ffmpeg_installed():
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def get_audio_info(audio_file):
    cmd = ['ffprobe', '-i', audio_file, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'json']
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])

def compress_audio(input_file, target_size=24.9 * 1024):
    output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
    duration = get_audio_info(input_file)
    target_bitrate = int((target_size * 8) / (1.048576 * duration))
    
    cmd = ['ffmpeg', '-i', input_file, '-b:a', f'{target_bitrate}k', '-y', output_file]
    subprocess.run(cmd, capture_output=True)
    return output_file

def calculate_bitrate(duration, target_size):
    bitrate = (target_size * 8) / (1.048576 * duration)
    return int(bitrate)

def is_valid_media_format(filename):
    valid_formats = [
        # Audio formats
        '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm',
        # Video formats
        '.avi', '.mov', '.mkv', '.flv', '.wmv'
    ]
    _, extension = os.path.splitext(filename)
    return extension.lower() in valid_formats

def is_video_format(filename):
    video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
    _, extension = os.path.splitext(filename)
    return extension.lower() in video_formats

def extract_audio_from_video(video_file_path):
    """Extract audio track from a video file using FFmpeg"""
    output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
    
    cmd = ['ffmpeg', '-i', video_file_path, '-vn', '-acodec', 'mp3', '-y', output_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Failed to extract audio from video: {result.stderr}")
    
    return output_file

def upload_to_tmpfiles(file_path):
    url = 'https://tmpfiles.org/api/v1/upload'
    
    try:
        # Create session without proxy settings
        session = requests.Session()
        session.trust_env = False
        
        with open(file_path, 'rb') as file:
            files = {'file': file}
            response = session.post(url, files=files, timeout=30)  # Add timeout
        
        if response.status_code == 200:
            try:
                response_data = json.loads(response.text)
                # The API returns a data URL, we need to modify it to get the direct file URL
                data_url = response_data['data']['url']
                file_url = data_url.replace('https://tmpfiles.org/', 'https://tmpfiles.org/dl/')
                return file_url
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Failed to parse tmpfiles.org response: {str(e)}")
        else:
            raise Exception(f"File upload failed with status code {response.status_code}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error during file upload: {str(e)}")

def transcribe_audio_groq(input_file, language="auto"):
    if not st.session_state.GROQ_API_KEY:
        raise ValueError("Groq API key is not set")
    
    # Initialize client with explicit API key
    try:
        client = Groq(api_key=st.session_state.GROQ_API_KEY)
        
        with open(input_file, "rb") as file:
            start_time = time.time()
            transcription = client.audio.transcriptions.create(
                file=(input_file, file.read()),
                model="whisper-large-v3",
                language=None if language == "auto" else language
            )
            end_time = time.time()
        return transcription.text, end_time - start_time
    except Exception as e:
        if "api_key" in str(e).lower():
            raise ValueError(f"Groq API key error: {str(e)}")
        else:
            raise Exception(f"Groq transcription error: {str(e)}")

def transcribe_audio_openai(input_file, language="auto"):
    if not st.session_state.OPENAI_API_KEY:
        raise ValueError("OpenAI API key is not set")
    
    # Use the newer OpenAI client syntax
    client = OpenAI(api_key=st.session_state.OPENAI_API_KEY)
    
    with open(input_file, "rb") as audio_file:
        start_time = time.time()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=None if language == "auto" else language
        )
        end_time = time.time()
    
    return transcript.text, end_time - start_time

def transcribe_audio_fal(input_file, language="auto"):
    if not st.session_state.FAL_KEY:
        raise ValueError("Fal API key is not set")
    
    try:
        # Make sure proxy settings are not used for this request
        session = requests.Session()
        session.trust_env = False  # Don't use environment variables for proxy settings
            
        url = "https://fal.run/fal-ai/wizper"
        headers = {
            "Authorization": f"Key {st.session_state.FAL_KEY}",
            "Content-Type": "application/json"
        }
        
        # Upload the file and get the URL
        with st.status("Uploading file to temporary storage...") as status:
            audio_url = upload_to_tmpfiles(input_file)
            status.update(label="File uploaded successfully. Sending to Fal API...", state="running")
        
        data = {
            "audio_url": audio_url,
            "task": "transcribe",
            "language": "auto" if language == "auto" else language,
            "chunk_level": "segment",
            "version": "3"
        }
        
        start_time = time.time()
        response = session.post(url, headers=headers, json=data, timeout=120)  # Add timeout
        end_time = time.time()
        
        if response.status_code == 200:
            try:
                result = response.json()
                return result["text"], end_time - start_time
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Failed to parse Fal API response: {str(e)}")
        else:
            raise Exception(f"Fal API request failed with status code {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error during Fal API request: {str(e)}")
    except Exception as e:
        if "API key" in str(e) or "authorization" in str(e).lower():
            raise ValueError(f"Fal API key error: {str(e)}")
        else:
            raise Exception(f"Fal transcription error: {str(e)}")

def save_transcript_to_file(transcript, filename):
    try:
        with open(filename, "w") as f:
            f.write(transcript)
        return True
    except Exception as e:
        st.error(f"Failed to save transcript: {str(e)}")
        return False

def add_logo():
    # Create a simple logo with text
    st.markdown("""
    <style>
    .logo-container {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    .logo-text {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1E88E5 0%, #9C27B0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-left: 10px;
    }
    .logo-icon {
        font-size: 2.5rem;
        color: #1E88E5;
    }
    </style>
    <div class="logo-container">
        <div class="logo-icon">🎙️</div>
        <div class="logo-text">Whisper Web UI</div>
    </div>
    """, unsafe_allow_html=True)

def apply_custom_css():
    # Apply custom CSS for better styling
    st.markdown("""
    <style>
    .stButton button {
        background-color: #4CAF50;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 8px 16px;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background-color: #45a049;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .success-message {
        padding: 10px;
        background-color: #dff0d8;
        border-left: 5px solid #3c763d;
        color: #3c763d;
        margin: 10px 0;
        border-radius: 4px;
    }
    .file-formats {
        font-size: 0.8rem;
        color: #666;
        margin-top: -15px;
        margin-bottom: 10px;
    }
    .dark-mode .file-formats {
        color: #aaa;
    }
    .dark-mode {
        background-color: #121212;
        color: #f0f0f0;
    }
    .dark-mode .stTextInput input, .dark-mode .stTextArea textarea {
        background-color: #2d2d2d;
        color: #f0f0f0;
        border-color: #444;
    }
    .dark-mode .stButton button {
        background-color: #388e3c;
    }
    .dark-mode .stButton button:hover {
        background-color: #2e7d32;
    }
    .dark-mode .success-message {
        background-color: #1b5e20;
        color: #a5d6a7;
        border-left: 5px solid #4caf50;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        border-radius: 4px 4px 0 0;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(128, 128, 128, 0.1);
        border-bottom: 2px solid #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    # Initialize session state variables
    if 'transcript' not in st.session_state:
        st.session_state.transcript = ""
    if 'transcription_time' not in st.session_state:
        st.session_state.transcription_time = 0
    if 'fal_disclaimer_accepted' not in st.session_state:
        st.session_state.fal_disclaimer_accepted = False
    if 'dark_mode' not in st.session_state:
        st.session_state.dark_mode = False
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'OPENAI_API_KEY' not in st.session_state:
        st.session_state.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    if 'GROQ_API_KEY' not in st.session_state:
        st.session_state.GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    if 'FAL_KEY' not in st.session_state:
        st.session_state.FAL_KEY = os.environ.get("FAL_KEY", "")
    
    # Apply dark mode if enabled
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
        .stApp {
            background-color: #121212;
            color: #f0f0f0;
        }
        </style>
        """, unsafe_allow_html=True)
    
    # Apply custom CSS
    apply_custom_css()
    
    # Create sidebar
    with st.sidebar:
        st.title("Settings")
        
        # Dark mode toggle
        st.session_state.dark_mode = st.toggle("Dark Mode", st.session_state.dark_mode)
        
        # API key input section
        with st.expander("API Settings", expanded=not st.session_state.OPENAI_API_KEY):
            st.session_state.OPENAI_API_KEY = st.text_input(
                "OpenAI API Key",
                value=st.session_state.OPENAI_API_KEY,
                type="password",
                help="Enter your OpenAI API key. Get one at https://platform.openai.com/api-keys"
            )
            
            st.session_state.GROQ_API_KEY = st.text_input(
                "Groq API Key (Optional)",
                value=st.session_state.GROQ_API_KEY,
                type="password",
                help="Enter your Groq API key. Get one at https://console.groq.com/keys"
            )
            
            st.session_state.FAL_KEY = st.text_input(
                "Fal API Key (Optional)",
                value=st.session_state.FAL_KEY,
                type="password",
                help="Enter your Fal API key if you want to use Fal."
            )
        
        # Language selection
        st.subheader("Language Settings")
        languages = {
            "auto": "Auto-detect",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ja": "Japanese",
            "zh": "Chinese",
            "ru": "Russian"
        }
        selected_language = st.selectbox(
            "Transcription Language", 
            options=list(languages.keys()), 
            format_func=lambda x: languages[x],
            index=0
        )
        
        # Recent transcriptions
        if st.session_state.history:
            st.subheader("Recent Transcriptions")
            for i, (timestamp, filename, transcript_snippet) in enumerate(st.session_state.history[-5:]):
                with st.expander(f"{filename} ({timestamp})"):
                    st.write(transcript_snippet[:100] + "..." if len(transcript_snippet) > 100 else transcript_snippet)
                    if st.button(f"Load", key=f"load_{i}"):
                        st.session_state.transcript = transcript_snippet
                        st.rerun()
    
    # Main content
    add_logo()
    
    # Check if ffmpeg is installed
    if not is_ffmpeg_installed():
        st.error("""
        ffmpeg is not installed or not in PATH. This application requires ffmpeg for audio processing.
        
        Installation instructions:
        
        Mac (using Homebrew):
        ```
        brew install ffmpeg
        ```
        
        Ubuntu/Debian:
        ```
        sudo apt update && sudo apt install ffmpeg
        ```
        
        Windows:
        Download from https://ffmpeg.org/download.html or install using Chocolatey:
        ```
        choco install ffmpeg
        ```
        
        After installation, please restart this application.
        """)
        st.stop()
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["📤 Upload & Transcribe", "✏️ Edit Transcript", "💾 Export"])
    
    with tab1:
        # API selection
        api_options = ["OpenAI"]
        if st.session_state.GROQ_API_KEY:
            api_options.append("Groq")
        if st.session_state.FAL_KEY:
            api_options.append("Fal")
            
        api_choice = st.radio("Select API for transcription:", api_options)

        # Disable transcription if required API key is missing
        api_key_missing = (
            (api_choice == "OpenAI" and not st.session_state.OPENAI_API_KEY) or
            (api_choice == "Groq" and not st.session_state.GROQ_API_KEY) or
            (api_choice == "Fal" and not st.session_state.FAL_KEY)
        )
        
        if api_key_missing:
            st.warning(f"Please enter your {api_choice} API key to use this option.")

        # Fal API disclaimer
        if api_choice == "Fal" and not st.session_state.fal_disclaimer_accepted:
            with st.expander("⚠️ Important Disclaimer for Fal API Usage", expanded=True):
                st.warning(
                    "By using the Fal API option, you agree to the following:\n\n"
                    "1. Your audio file will be uploaded to tmpfiles.org.\n"
                    "2. The uploaded file will be publicly accessible for 60 minutes.\n"
                    "3. After 60 minutes, the file will be automatically deleted from tmpfiles.org.\n\n"
                    "This is necessary because the Fal API requires a URL\n\n"
                    "Please ensure that you have the necessary rights to upload and make your audio file temporarily public."
                )
                st.session_state.fal_disclaimer_accepted = st.checkbox("I understand and agree to proceed")

        if (api_choice != "Fal" or st.session_state.fal_disclaimer_accepted) and not api_key_missing:
            st.subheader("Upload Audio or Video File")
            uploaded_file = st.file_uploader("Choose an audio or video file", type=["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "avi", "mov", "mkv", "flv", "wmv"])
            st.markdown('<p class="file-formats">Supported formats: MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM, AVI, MOV, MKV, FLV, WMV</p>', unsafe_allow_html=True)

            if uploaded_file is not None:
                # Determine if the file is a video
                is_video = is_video_format(uploaded_file.name)
                
                # Display appropriate preview
                if is_video:
                    st.video(uploaded_file)
                else:
                    st.audio(uploaded_file, format="audio/mp3")

                col1, col2 = st.columns([1, 1])
                with col1:
                    process_button = st.button("🔊 Transcribe Media", use_container_width=True)
                
                if process_button:
                    with st.status("Processing media...", expanded=True) as status:
                        # Save uploaded file temporarily
                        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1])
                        temp_input.write(uploaded_file.getvalue())
                        temp_input.close()

                        file_size = os.path.getsize(temp_input.name) / (1024 * 1024)  # File size in MB
                        status.update(label=f"Input file size: {file_size:.2f} MB", state="running")
                        
                        # Process video if needed
                        if is_video:
                            status.update(label="Extracting audio from video...", state="running")
                            try:
                                audio_file = extract_audio_from_video(temp_input.name)
                                status.update(label="Audio extraction complete.", state="running")
                            except Exception as e:
                                st.error(f"Failed to extract audio from video: {str(e)}")
                                status.update(label="Failed to extract audio from video.", state="error")
                                # Cleanup
                                if os.path.exists(temp_input.name):
                                    os.unlink(temp_input.name)
                                st.stop()
                        else:
                            audio_file = temp_input.name

                        # Check if compression is needed
                        audio_file_size = os.path.getsize(audio_file) / (1024 * 1024)  # Audio file size in MB
                        if audio_file_size > 25:
                            status.update(label="File size exceeds 25MB. Compressing...", state="running")
                            input_file = compress_audio(audio_file)
                            status.update(label="Compression complete.", state="running")
                        else:
                            status.update(label="File size is within the allowed limit. No compression needed.", state="running")
                            input_file = audio_file

                        status.update(label=f"Transcribing audio using {api_choice} API...", state="running")
                        try:
                            if api_choice == "OpenAI":
                                st.session_state.transcript, st.session_state.transcription_time = transcribe_audio_openai(
                                    input_file, 
                                    language=selected_language
                                )
                            elif api_choice == "Groq":
                                st.session_state.transcript, st.session_state.transcription_time = transcribe_audio_groq(
                                    input_file,
                                    language=selected_language
                                )
                            else:  # Fal
                                st.session_state.transcript, st.session_state.transcription_time = transcribe_audio_fal(
                                    input_file,
                                    language=selected_language
                                )
                            
                            # Add to history
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                            st.session_state.history.append((timestamp, uploaded_file.name, st.session_state.transcript))
                            # Keep only the last 10 items
                            st.session_state.history = st.session_state.history[-10:]
                            
                            status.update(label=f"Transcription complete! Time taken: {st.session_state.transcription_time:.2f} seconds", state="complete")
                        except Exception as e:
                            error_msg = str(e)
                            st.error(f"Transcription failed: {error_msg}")
                            
                            if "proxies" in error_msg.lower() or "proxy" in error_msg.lower():
                                st.error("""
                                Proxy configuration issue detected! Try one of these solutions:
                                
                                1. Run the application without proxy environment variables:
                                   ```
                                   env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy streamlit run whisper_webui.py
                                   ```
                                   
                                2. Update your packages:
                                   ```
                                   pip install -U openai httpx
                                   ```
                                   
                                3. Restart the application after clearing environment variables.
                                """)
                            elif "api key" in error_msg.lower():
                                st.error("Please check that your API key is correct and has been entered properly.")
                            elif "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                                st.error("You may have hit a rate limit or quota on your API key. Please check your usage.")
                            elif "network" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                                st.error("Network error detected. Please check your internet connection.")
                            elif "file" in error_msg.lower() and ("not found" in error_msg.lower() or "access" in error_msg.lower()):
                                st.error("File access error. The temporary file may have been deleted or is inaccessible.")
                            elif "format" in error_msg.lower() or "codec" in error_msg.lower():
                                st.error("Audio format error. The file may be corrupted or in an unsupported format.")
                            elif "ffmpeg" in error_msg.lower():
                                st.error("FFmpeg error. Please ensure FFmpeg is properly installed on your system.")
                            elif "memory" in error_msg.lower():
                                st.error("Memory error. The file may be too large to process with available memory.")

                        # Cleanup temporary files
                        try:
                            if os.path.exists(temp_input.name):
                                os.unlink(temp_input.name)
                            if is_video and os.path.exists(audio_file) and audio_file != input_file:
                                os.unlink(audio_file)
                            if audio_file_size > 25 and os.path.exists(input_file) and input_file != audio_file:
                                os.unlink(input_file)
                        except Exception as e:
                            st.warning(f"Warning: Could not clean up temporary files: {str(e)}")
    
    with tab2:
        # Edit transcript
        if st.session_state.transcript:
            st.subheader("Edit Transcript")
            st.session_state.transcript = st.text_area(
                "Edit as needed:", 
                value=st.session_state.transcript, 
                height=400
            )
        else:
            st.info("No transcript available. Please upload and transcribe an audio file first.")
    
    with tab3:
        # Export options
        if st.session_state.transcript:
            st.subheader("Export Options")
            
            # Copy to clipboard button
            if st.button("📋 Copy to Clipboard", use_container_width=True):
                try:
                    pyperclip.copy(st.session_state.transcript)
                    st.markdown('<div class="success-message">✅ Transcript copied to clipboard!</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Failed to copy to clipboard: {str(e)}")
            
            # Save to file section
            st.subheader("Save Transcript to File")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                output_filename = st.text_input("Enter output filename:", value=f"transcript_{int(time.time())}")
            with col2:
                file_format = st.selectbox("Format:", ["txt", "md"])
            
            if st.button("💾 Save Transcript", use_container_width=True):
                if output_filename:
                    # Add extension if not present
                    if not output_filename.endswith(f".{file_format}"):
                        output_filename = f"{output_filename}.{file_format}"
                    
                    if save_transcript_to_file(st.session_state.transcript, output_filename):
                        st.markdown(f'<div class="success-message">✅ Transcript saved to {output_filename}</div>', unsafe_allow_html=True)
                else:
                    st.warning("Please enter a filename to save the transcript.")
        else:
            st.info("No transcript available. Please upload and transcribe an audio file first.")

if __name__ == '__main__':
    main()

