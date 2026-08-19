import subprocess
import sys
import os
import re
import librosa
import numpy as np
from scipy import signal
from datetime import datetime

def list_latest_file(directory, extension=".webm"):
    result = subprocess.run(["uvx", "fulcra-api", "file", "list", directory], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
    
    valid_files = []
    for line in lines:
        filename = line.split()[-1]
        if filename.endswith(extension):
            match = re.search(r'(\d{8}_\d{6})', filename)
            if match:
                valid_files.append((match.group(1), filename))
    
    if not valid_files:
        return None
        
    valid_files.sort(key=lambda x: x[0])
    latest_file = valid_files[-1][1]
    return f"{directory}{latest_file}"

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h_{minutes:02d}m_{secs:02d}s"
    return f"{minutes:02d}m_{secs:02d}s"

def detect_key_and_bpm(audio_path):
    print(f"   -> Analyzing musical properties of {audio_path}...")
    y, sr = librosa.load(audio_path, sr=22050)
    
    # 1. BPM Detection
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(np.round(tempo[0] if isinstance(tempo, np.ndarray) else tempo))
    
    # 2. Key Signature Detection (Krumhansl-Schmuckler approach simplified)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_sum = np.sum(chroma, axis=1)
    
    # Krumhansl-Schmuckler profiles
    maj_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    min_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    
    pitches = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    best_corr = -1
    best_key = "Unknown"
    
    for i in range(12):
        # Rotate profiles to test all 12 roots
        rotated_maj = np.roll(maj_profile, i)
        rotated_min = np.roll(min_profile, i)
        
        corr_maj = np.corrcoef(chroma_sum, rotated_maj)[0, 1]
        corr_min = np.corrcoef(chroma_sum, rotated_min)[0, 1]
        
        if corr_maj > best_corr:
            best_corr = corr_maj
            best_key = f"{pitches[i]} Major"
        if corr_min > best_corr:
            best_corr = corr_min
            best_key = f"{pitches[i]} minor"
            
    # Clean string for tagging (e.g. "C# Major" -> "C#-Major")
    safe_key = best_key.replace(" ", "-")
    return safe_key, bpm

def main():
    print("--- Flow State: Background DSP Processor ---")
    
    raw_session = list_latest_file("/agent/flow-state/sessions/raw/")
    marker_template = list_latest_file("/agent/flow-state/templates/")
    
    if not raw_session or not marker_template:
        print("❌ Could not find raw session or marker template in Fulcra.")
        sys.exit(1)
        
    session_filename = raw_session.split('/')[-1]
    session_basename = session_filename.replace('.webm', '')
    
    local_raw_session = f"temp_{session_filename}"
    local_raw_marker = "temp_marker.webm"
    
    hq_session_wav = f"{session_basename}_hq.wav"
    hq_marker_wav = "marker_hq.wav"
    
    print(f"1. Downloading latest session ({session_filename}) and marker...")
    subprocess.run(["uvx", "fulcra-api", "file", "download", raw_session, local_raw_session], check=True)
    subprocess.run(["uvx", "fulcra-api", "file", "download", marker_template, local_raw_marker], check=True)
    
    print("2. Transcoding and fixing headers (HQ 44.1kHz Stereo WAV)...")
    subprocess.run([
        "ffmpeg", "-y", "-err_detect", "ignore_err", 
        "-i", local_raw_session, 
        "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", 
        "-max_muxing_queue_size", "1024",
        hq_session_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    subprocess.run([
        "ffmpeg", "-y", "-err_detect", "ignore_err", 
        "-i", local_raw_marker, 
        "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", 
        "-max_muxing_queue_size", "1024",
        hq_marker_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    processed_fulcra = f"/agent/flow-state/sessions/processed/{session_basename}.wav"
    print(f"3. Uploading HQ processed session to {processed_fulcra}...")
    subprocess.run(["uvx", "fulcra-api", "file", "upload", hq_session_wav, processed_fulcra], check=True)
    
    print("4. Loading audio into Librosa for DSP analysis (downsampling to 22050Hz for math)...")
    y_session, sr = librosa.load(hq_session_wav, sr=22050)
    y_marker_raw, _ = librosa.load(hq_marker_wav, sr=22050)
    
    print("   -> Normalizing audio to 0 dB to fix low-gain mobile recordings...")
    y_session = librosa.util.normalize(y_session)
    y_marker_raw = librosa.util.normalize(y_marker_raw)
    
    y_marker, _ = librosa.effects.trim(y_marker_raw, top_db=25)
    
    print("5. Calculating Normalized MFCC Cross-Correlation...")
    mfcc_session = librosa.feature.mfcc(y=y_session, sr=sr)
    mfcc_marker = librosa.feature.mfcc(y=y_marker, sr=sr)
    
    mfcc_session = (mfcc_session - np.mean(mfcc_session, axis=1, keepdims=True)) / (np.std(mfcc_session, axis=1, keepdims=True) + 1e-8)
    mfcc_marker = (mfcc_marker - np.mean(mfcc_marker, axis=1, keepdims=True)) / (np.std(mfcc_marker, axis=1, keepdims=True) + 1e-8)
    
    res = np.zeros(mfcc_session.shape[1] - mfcc_marker.shape[1] + 1)
    for i in range(mfcc_marker.shape[0]):
        res += signal.correlate(mfcc_session[i], mfcc_marker[i], mode='valid')
        
    threshold = np.max(res) * 0.94 # Extremely strict threshold to reject mobile mic noise
    min_distance = librosa.time_to_frames(5.0, sr=sr)
    
    peaks, _ = signal.find_peaks(res, height=threshold, distance=min_distance)
    
    if len(peaks) == 0:
        print("❌ No markers found matching the template.")
    else:
        print(f"🎯 Found {len(peaks)} marker(s)!")
        
        session_datetime = "unknown_date"
        match = re.search(r'(\d{8}_\d{6})', session_basename)
        if match:
            session_datetime = match.group(1)
        
        for idx, peak_frame in enumerate(peaks):
            best_time = librosa.frames_to_time(peak_frame, sr=sr)
            human_time = format_timestamp(best_time)
            print(f"\n   --- Processing Marker #{idx+1} at {human_time} ---")
            
            lookback = 15.0
            start_time = max(0, best_time - lookback)
            duration = best_time - start_time
            if duration <= 0:
                start_time = 0
                duration = 10.0
                
            idea_wav = f"Idea_{session_datetime}_at_{human_time}.wav"
            subprocess.run(["ffmpeg", "-y", "-ss", str(start_time), "-t", str(duration), "-i", hq_session_wav, idea_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Analyze Key & BPM
            detected_key, detected_bpm = detect_key_and_bpm(idea_wav)
            print(f"   -> Detected Key: {detected_key} | BPM: {detected_bpm}")
            
            idea_fulcra = f"/agent/flow-state/ideas/{idea_wav}"
            print(f"   -> Uploading extracted idea to {idea_fulcra}...")
            subprocess.run(["uvx", "fulcra-api", "file", "upload", idea_wav, idea_fulcra], check=True)
            
            # Fetch the exact ID string of the user's `MusicalIdea` data type dynamically
            print("6. Looking up user's MusicalIdea data type ID...")
            type_res = subprocess.run(["uvx", "fulcra-api", "catalog", "--category", "user_configured"], capture_output=True, text=True, check=True)
            musical_idea_id = None
            
            import json
            for line in type_res.stdout.strip().split('\n'):
                if not line.strip(): continue
                try:
                    item = json.loads(line)
                    if item.get("name") == "MusicalIdea":
                        musical_idea_id = item.get("id")
                        break
                except json.JSONDecodeError:
                    continue
            
            if not musical_idea_id:
                print("❌ Error: MusicalIdea data type not found in this Fulcra account. Cannot upload semantic record.")
                return
            # Pipe an empty JSON object into the CLI to satisfy the input requirement
            cmd = f"echo '{{}}' | uvx fulcra-api record {musical_idea_id} --note 'Extracted from {session_filename}. File: {idea_fulcra}' --tag 'key:{detected_key}' --tag 'bpm:{detected_bpm}' --tag 'flow-state-app'"
            subprocess.run(cmd, shell=True, check=True)
            
            if os.path.exists(idea_wav):
                os.remove(idea_wav)
    
    print("\nCleaning up...")
    for f in [local_raw_session, local_raw_marker, hq_session_wav, hq_marker_wav]:
        if os.path.exists(f):
            os.remove(f)
            
    print("✅ Background processing complete.")

if __name__ == "__main__":
    main()
