import argparse
import os
import time
from pydub import AudioSegment
from openai import OpenAI
from groq import Groq
import pyperclip
import subprocess

def get_audio_info(input_file):
    print(f"Loading audio file: {input_file}")
    audio = AudioSegment.from_file(input_file)
    duration = len(audio) / 1000  # Duration in seconds
    print(f"Audio duration: {duration:.2f} seconds")
    return duration

def calculate_bitrate(input_file, target_size):
    duration = get_audio_info(input_file)
    bitrate = (target_size * 8) / (1.048576 * duration)
    print(f"Calculated bitrate: {bitrate:.2f} kbps")
    return int(bitrate)

def compress_audio(input_file, output_file, bitrate):
    print(f"Compressing audio file: {input_file}")
    start_time = time.time()
    audio = AudioSegment.from_file(input_file)
    print(f"Exporting compressed audio to: {output_file}")
    audio.export(output_file, format='mp3', bitrate=f'{bitrate}k')
    end_time = time.time()
    compression_time = end_time - start_time
    print(f"Audio compression completed in {compression_time:.2f} seconds.")

def is_valid_media_format(input_file):
    valid_formats = [
        # Audio formats
        '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm',
        # Video formats
        '.avi', '.mov', '.mkv', '.flv', '.wmv'
    ]
    _, extension = os.path.splitext(input_file)
    return extension.lower() in valid_formats

def is_video_format(input_file):
    video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
    _, extension = os.path.splitext(input_file)
    return extension.lower() in video_formats

def extract_audio_from_video(video_file_path, output_file=None):
    """Extract audio track from a video file using FFmpeg"""
    if output_file is None:
        output_file = f"{os.path.splitext(video_file_path)[0]}_audio.mp3"
    
    print(f"Extracting audio from video: {video_file_path}")
    start_time = time.time()
    
    cmd = ['ffmpeg', '-i', video_file_path, '-vn', '-acodec', 'mp3', '-y', output_file]
    subprocess.run(cmd, check=True)
    
    end_time = time.time()
    extraction_time = end_time - start_time
    print(f"Audio extraction completed in {extraction_time:.2f} seconds.")
    
    return output_file

def transcribe_audio_openai(input_file, output_file, copy_to_clipboard):
    print(f"Transcribing audio file using OpenAI: {input_file}")
    
    # Check if API key is set
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return
    
    client = OpenAI(api_key=api_key)
    
    try:
        start_time = time.time()
        
        with open(input_file, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        
        end_time = time.time()
        transcription_time = end_time - start_time
        
        print(f"Transcription completed in {transcription_time:.2f} seconds.")
        save_transcript(transcript.text, output_file, copy_to_clipboard)
        
    except Exception as e:
        print(f"Error during transcription: {str(e)}")

def transcribe_audio_groq(input_file, output_file, copy_to_clipboard):
    print(f"Transcribing audio file using Groq: {input_file}")
    
    # Check if API key is set
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY environment variable not set.")
        return
    
    client = Groq(api_key=api_key)
    
    try:
        start_time = time.time()
        
        with open(input_file, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        
        end_time = time.time()
        transcription_time = end_time - start_time
        
        print(f"Transcription completed in {transcription_time:.2f} seconds.")
        save_transcript(transcript.text, output_file, copy_to_clipboard)
        
    except Exception as e:
        print(f"Error during transcription: {str(e)}")

def save_transcript(transcript, output_file, copy_to_clipboard):
    with open(output_file, "w") as transcript_file:
        transcript_file.write(transcript)
    print(f"Transcript saved to: {output_file}")

    if copy_to_clipboard:
        pyperclip.copy(transcript)
        print("Transcription text copied to clipboard.")

def main():
    parser = argparse.ArgumentParser(description='Transcribe audio files using OpenAI Whisper API or Groq API')
    parser.add_argument('input_file', help='Path to the audio or video file to transcribe')
    parser.add_argument('-o', '--output', help='Output file for the transcript (default: input_file_transcript.txt)')
    parser.add_argument('-c', '--copy', action='store_true', help='Copy transcript to clipboard')
    parser.add_argument('--compress-only', action='store_true', help='Only compress the audio file, do not transcribe')
    parser.add_argument('--api', choices=['openai', 'groq'], default='openai', help='API to use for transcription (default: openai)')
    
    args = parser.parse_args()
    
    input_file = args.input_file
    
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        return
    
    if not is_valid_media_format(input_file):
        print('Invalid media format. Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm, avi, mov, mkv, flv, wmv')
        return

    if is_video_format(input_file):
        input_file = extract_audio_from_video(input_file)
    else:
        file_size = os.path.getsize(input_file) / (1024 * 1024)  # File size in MB
        print(f"Input file size: {file_size:.2f} MB")

        if file_size > 25:
            target_size = 24.9 * 1024  # Target size in kilobytes (just under 25MB)
            print(f"Target size: {target_size} KB")

            bitrate = calculate_bitrate(input_file, target_size)

            compressed_file = f'{os.path.splitext(input_file)[0]}_compressed.mp3'
            compress_audio(input_file, compressed_file, bitrate)
            input_file = compressed_file
        else:
            print("Input file size is within the allowed limit. No compression needed.")

    if not args.compress_only:
        if args.output is None:
            output_file = f'{os.path.splitext(input_file)[0]}_transcript.txt'
        else:
            output_file = args.output
        
        api_choice = args.api
        if api_choice == 'openai':
            transcribe_audio_openai(input_file, output_file, args.copy)
        else:
            transcribe_audio_groq(input_file, output_file, args.copy)

if __name__ == '__main__':
    main()