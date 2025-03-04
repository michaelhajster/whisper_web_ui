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
import re
import sqlite3
from datetime import datetime
from groq import Groq
from openai import OpenAI  # Updated import
import yt_dlp  # Added for YouTube downloading

# Database setup
def get_db_path():
    """Get the path to the SQLite database file."""
    # Create a data directory in the same folder as the script
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "transcription_history.db")

def init_db():
    """Initialize the database with the necessary tables."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    # Create transcriptions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transcriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        api_used TEXT NOT NULL,
        language TEXT NOT NULL,
        duration REAL,
        transcript TEXT NOT NULL,
        favorite BOOLEAN DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()

def save_transcription(source_name, source_type, api_used, language, duration, transcript):
    """Save a transcription to the database."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
    INSERT INTO transcriptions 
    (timestamp, source_name, source_type, api_used, language, duration, transcript)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, source_name, source_type, api_used, language, duration, transcript))
    
    conn.commit()
    conn.close()
    
    return cursor.lastrowid

def get_transcription_history(limit=100, offset=0, search_term=None):
    """Get transcription history from the database."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    if search_term:
        cursor.execute('''
        SELECT id, timestamp, source_name, source_type, api_used, language, duration, transcript, favorite
        FROM transcriptions
        WHERE transcript LIKE ? OR source_name LIKE ?
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        ''', (f'%{search_term}%', f'%{search_term}%', limit, offset))
    else:
        cursor.execute('''
        SELECT id, timestamp, source_name, source_type, api_used, language, duration, transcript, favorite
        FROM transcriptions
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        ''', (limit, offset))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

def get_transcription_by_id(transcription_id):
    """Get a specific transcription by ID."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, timestamp, source_name, source_type, api_used, language, duration, transcript, favorite
    FROM transcriptions
    WHERE id = ?
    ''', (transcription_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result

def toggle_favorite(transcription_id, favorite_status):
    """Toggle the favorite status of a transcription."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE transcriptions
    SET favorite = ?
    WHERE id = ?
    ''', (1 if favorite_status else 0, transcription_id))
    
    conn.commit()
    conn.close()

def delete_transcription(transcription_id):
    """Delete a transcription from the database."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    
    cursor.execute('''
    DELETE FROM transcriptions
    WHERE id = ?
    ''', (transcription_id,))
    
    conn.commit()
    conn.close()

def export_transcriptions_to_json(file_path):
    """Export all transcriptions to a JSON file."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, timestamp, source_name, source_type, api_used, language, duration, transcript, favorite
    FROM transcriptions
    ORDER BY timestamp DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    # Convert rows to dictionaries
    transcriptions = []
    for row in rows:
        transcriptions.append(dict(row))
    
    with open(file_path, 'w') as f:
        json.dump(transcriptions, f, indent=4)

# Initialize database at startup
init_db()

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

def is_valid_youtube_url(url):
    """Check if the URL is a valid YouTube URL."""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    match = re.match(youtube_regex, url)
    return bool(match)

def get_youtube_video_id(url):
    """Extract the video ID from a YouTube URL."""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    match = re.match(youtube_regex, url)
    if match:
        return match.group(6)
    return None

def download_youtube_audio(url, progress_callback=None):
    """Download audio from a YouTube video."""
    # Create a temporary directory to store files
    temp_dir = tempfile.mkdtemp()
    temp_base = os.path.join(temp_dir, "youtube_audio")
    output_file = f"{temp_base}.mp3"
    
    # More reliable options for yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'paths': {'temp': temp_dir, 'home': temp_dir},
        'outtmpl': temp_base,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,  # Continue on download errors
        'nooverwrites': False, # Overwrite existing files
        'writethumbnail': False,
        'verbose': False
    }
    
    if progress_callback:
        ydl_opts['progress_hooks'] = [progress_callback]
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise Exception("Failed to extract video information")
        
        # Check for the expected output file
        expected_output = f"{temp_base}.mp3"
        if os.path.exists(expected_output):
            return expected_output
            
        # If the expected file doesn't exist, look for any audio file in the temp directory
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp3', '.m4a', '.wav', '.aac')):
                return os.path.join(temp_dir, file)
                
        # If we still don't have a file, try a direct approach with ffmpeg
        video_id = get_youtube_video_id(url)
        if video_id:
            direct_url = f"https://www.youtube.com/watch?v={video_id}"
            fallback_output = os.path.join(temp_dir, "direct_audio.mp3")
            cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '-o', fallback_output, direct_url]
            subprocess.run(cmd, check=True, capture_output=True)
            if os.path.exists(fallback_output):
                return fallback_output
                
        raise Exception("No audio file was downloaded")
    except Exception as e:
        # Clean up temp directory on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise Exception(f"Failed to download YouTube video: {str(e)}")

def is_ytdlp_installed():
    """Check if yt-dlp is installed and working properly."""
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def download_youtube_audio_direct(url):
    """Download audio from a YouTube video using direct command-line approach."""
    temp_dir = tempfile.mkdtemp()
    output_file = os.path.join(temp_dir, "audio.mp3")
    
    # Try yt-dlp first
    try:
        cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '-o', output_file, url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.exists(output_file):
            return output_file
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Try youtube-dl as fallback
    try:
        cmd = ['youtube-dl', '-x', '--audio-format', 'mp3', '-o', output_file, url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.exists(output_file):
            return output_file
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # If both failed, try ffmpeg directly if we can get a direct stream URL
    try:
        # Get stream URL using yt-dlp
        cmd = ['yt-dlp', '-f', 'bestaudio', '-g', url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stream_url = result.stdout.strip()
        
        if stream_url:
            # Download with ffmpeg
            cmd = ['ffmpeg', '-i', stream_url, '-acodec', 'mp3', '-y', output_file]
            subprocess.run(cmd, capture_output=True, check=True)
            if os.path.exists(output_file):
                return output_file
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Clean up if all methods failed
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise Exception("Failed to download YouTube audio using all available methods")

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
    
    # Check if yt-dlp is installed
    ytdlp_installed = is_ytdlp_installed()
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload & Transcribe", "✏️ Edit Transcript", "💾 Export", "📚 History"])
    
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

            # Add YouTube URL input
            st.subheader("Or Transcribe from YouTube")
            
            if not ytdlp_installed:
                st.warning("""
                yt-dlp is not installed or not working properly. YouTube transcription requires yt-dlp.
                
                Installation instructions:
                
                ```
                pip install yt-dlp
                ```
                
                After installation, please restart this application.
                """)
            else:
                youtube_url = st.text_input("Enter YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
                is_valid_url = is_valid_youtube_url(youtube_url) if youtube_url else False
                
                if youtube_url and not is_valid_url:
                    st.error("Please enter a valid YouTube URL")
                elif youtube_url and is_valid_url:
                    video_id = get_youtube_video_id(youtube_url)
                    st.video(f"https://www.youtube.com/watch?v={video_id}")
                    
                    youtube_process_button = st.button("🎬 Transcribe YouTube Video", use_container_width=True)
                    
                    if youtube_process_button:
                        with st.status("Processing YouTube video...", expanded=True) as status:
                            try:
                                # Download YouTube audio
                                status.update(label="Downloading audio from YouTube...", state="running")
                                
                                # Define progress callback
                                progress_placeholder = st.empty()
                                
                                def yt_progress_hook(d):
                                    if d['status'] == 'downloading':
                                        try:
                                            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                                            downloaded = d.get('downloaded_bytes', 0)
                                            if total_bytes > 0:
                                                progress = (downloaded / total_bytes) * 100
                                                progress_placeholder.progress(int(progress))
                                                status.update(label=f"Downloading: {progress:.1f}% of {total_bytes/1024/1024:.1f} MB", state="running")
                                        except:
                                            pass
                                
                                # Download the audio
                                try:
                                    audio_file = download_youtube_audio(youtube_url, yt_progress_hook)
                                    status.update(label="Download complete!", state="running")
                                except Exception as e:
                                    status.update(label="Primary download method failed. Trying alternative method...", state="running")
                                    try:
                                        audio_file = download_youtube_audio_direct(youtube_url)
                                        status.update(label="Download complete using alternative method!", state="running")
                                    except Exception as e2:
                                        raise Exception(f"All download methods failed. Primary error: {str(e)}. Secondary error: {str(e2)}")
                                
                                # Check if compression is needed
                                audio_file_size = os.path.getsize(audio_file) / (1024 * 1024)  # Audio file size in MB
                                if audio_file_size > 25:
                                    status.update(label="File size exceeds 25MB. Compressing...", state="running")
                                    input_file = compress_audio(audio_file)
                                    status.update(label="Compression complete.", state="running")
                                else:
                                    status.update(label="File size is within the allowed limit. No compression needed.", state="running")
                                    input_file = audio_file
                                
                                # Transcribe the audio
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
                                    video_title = f"YouTube: {video_id}"
                                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                                    st.session_state.history.append((timestamp, video_title, st.session_state.transcript))
                                    # Keep only the last 10 items
                                    st.session_state.history = st.session_state.history[-10:]
                                    
                                    # Save to database
                                    try:
                                        # Get duration if available
                                        duration = None
                                        try:
                                            duration = get_audio_info(input_file)
                                        except:
                                            pass
                                            
                                        save_transcription(
                                            source_name=video_title,
                                            source_type="youtube",
                                            api_used=api_choice,
                                            language=selected_language,
                                            duration=duration,
                                            transcript=st.session_state.transcript
                                        )
                                    except Exception as db_error:
                                        st.warning(f"Failed to save to history database: {str(db_error)}")
                                    
                                    status.update(label=f"Transcription complete! Time taken: {st.session_state.transcription_time:.2f} seconds", state="complete")
                                except Exception as e:
                                    error_msg = str(e)
                                    st.error(f"Transcription failed: {error_msg}")
                                    status.update(label="Transcription failed.", state="error")
                                
                                # Cleanup
                                if os.path.exists(audio_file):
                                    os.unlink(audio_file)
                                if 'input_file' in locals() and input_file != audio_file and os.path.exists(input_file):
                                    os.unlink(input_file)
                                    
                            except Exception as e:
                                st.error(f"Failed to process YouTube video: {str(e)}")
                                status.update(label="Failed to process YouTube video.", state="error")

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
                            
                            # Save to database
                            try:
                                # Get duration if available
                                duration = None
                                try:
                                    duration = get_audio_info(input_file)
                                except:
                                    pass
                                    
                                save_transcription(
                                    source_name=uploaded_file.name,
                                    source_type="local",
                                    api_used=api_choice,
                                    language=selected_language,
                                    duration=duration,
                                    transcript=st.session_state.transcript
                                )
                            except Exception as db_error:
                                st.warning(f"Failed to save to history database: {str(db_error)}")
                            
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

    with tab4:
        # History tab
        st.subheader("📚 Transcription History")
        
        # Search functionality
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_term = st.text_input("Search transcriptions", placeholder="Enter keywords to search...")
        with search_col2:
            st.write("")
            st.write("")
            show_favorites_only = st.checkbox("Favorites only")
        
        # Get transcription history from database
        history = get_transcription_history(limit=100, search_term=search_term if search_term else None)
        
        if not history:
            st.info("No transcription history found in the database.")
        else:
            # Display history in a table
            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1, 1])
            col1.subheader("Source")
            col2.subheader("Date")
            col3.subheader("API")
            col4.subheader("Type")
            col5.subheader("Actions")
            
            for record in history:
                id, timestamp, source_name, source_type, api_used, language, duration, transcript, favorite = record
                
                # Skip non-favorites if showing favorites only
                if show_favorites_only and not favorite:
                    continue
                
                with st.expander(f"{source_name} ({timestamp})"):
                    st.markdown(f"**Source:** {source_name}")
                    st.markdown(f"**Date:** {timestamp}")
                    st.markdown(f"**API Used:** {api_used}")
                    st.markdown(f"**Language:** {language}")
                    if duration:
                        st.markdown(f"**Duration:** {duration:.2f} seconds")
                    
                    # Display transcript with copy button
                    st.text_area("Transcript", transcript, height=200, key=f"transcript_{id}")
                    
                    # Action buttons
                    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                    
                    with col1:
                        if st.button("Load to Editor", key=f"load_{id}"):
                            st.session_state.transcript = transcript
                            st.rerun()
                    
                    with col2:
                        if st.button("Copy", key=f"copy_{id}"):
                            pyperclip.copy(transcript)
                            st.success("Copied to clipboard!")
                    
                    with col3:
                        if favorite:
                            if st.button("Unfavorite", key=f"unfav_{id}"):
                                toggle_favorite(id, False)
                                st.rerun()
                        else:
                            if st.button("Favorite", key=f"fav_{id}"):
                                toggle_favorite(id, True)
                                st.rerun()
                    
                    with col4:
                        if st.button("Delete", key=f"del_{id}"):
                            delete_transcription(id)
                            st.success("Transcription deleted!")
                            st.rerun()
            
            # Export functionality
            st.subheader("Export History")
            export_col1, export_col2 = st.columns([3, 1])
            with export_col1:
                export_path = st.text_input("Export path", "transcription_history.json")
            with export_col2:
                st.write("")
                st.write("")
                if st.button("Export to JSON"):
                    try:
                        export_transcriptions_to_json(export_path)
                        st.success(f"Successfully exported to {export_path}")
                    except Exception as e:
                        st.error(f"Export failed: {str(e)}")

if __name__ == '__main__':
    main()

