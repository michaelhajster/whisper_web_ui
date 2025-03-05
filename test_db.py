import os
import sqlite3
from datetime import datetime

# Import database functions from whisper_webui.py
from whisper_webui import get_db_path, save_transcription, get_transcription_history, get_transcription_by_id, toggle_favorite, delete_transcription

def test_database_functionality():
    """Test the database functionality end-to-end."""
    print("Testing database functionality...")
    
    # 1. Get database path
    db_path = get_db_path()
    print(f"Database path: {db_path}")
    
    # 2. Check if database exists
    if os.path.exists(db_path):
        print("Database file exists.")
    else:
        print("Database file does not exist!")
        return
    
    # 3. Add a test transcription
    test_transcript = "This is a test transcription to verify database functionality."
    transcription_id = save_transcription(
        source_name="test_file.mp3",
        source_type="test",
        api_used="test",
        language="en",
        duration=60.0,
        transcript=test_transcript
    )
    print(f"Added test transcription with ID: {transcription_id}")
    
    # 4. Retrieve the transcription
    history = get_transcription_history(limit=10)
    print(f"Found {len(history)} transcriptions in history.")
    
    if history:
        # Get the latest transcription
        latest = history[0]
        print(f"Latest transcription: ID={latest[0]}, Source={latest[2]}, API={latest[4]}")
        
        # 5. Get by ID
        transcription = get_transcription_by_id(latest[0])
        if transcription:
            print(f"Retrieved transcription by ID: {transcription[0]}")
            print(f"Transcript: {transcription[7][:50]}...")
        else:
            print("Failed to retrieve transcription by ID!")
        
        # 6. Toggle favorite
        toggle_favorite(latest[0], True)
        print(f"Marked transcription {latest[0]} as favorite.")
        
        # 7. Verify favorite status
        transcription = get_transcription_by_id(latest[0])
        print(f"Favorite status: {bool(transcription[8])}")
        
        # 8. Delete the test transcription
        delete_transcription(latest[0])
        print(f"Deleted transcription {latest[0]}.")
        
        # 9. Verify deletion
        remaining = get_transcription_history(limit=10)
        print(f"Remaining transcriptions: {len(remaining)}")
    
    print("Database test completed.")

if __name__ == "__main__":
    test_database_functionality() 