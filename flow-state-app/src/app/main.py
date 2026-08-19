from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import subprocess
import tempfile
import os
import sys
import json
import re
import asyncio
from datetime import datetime

app = FastAPI(title="Flow State Web App")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("app/static/index.html")


@app.get("/api/audio")
def get_audio(path: str):
    import tempfile
    import os
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    
    # Simple validation to ensure it looks like a Fulcra path
    if not path.startswith("/agent/"):
        raise HTTPException(status_code=400, detail="Invalid path")
        
    # Create a temporary file to download into with correct extension
    ext = os.path.splitext(path)[1] or '.wav'
    fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    
    try:
        # Download the file from Fulcra
        subprocess.run(["uvx", "fulcra-api", "file", "download", path, temp_path], check=True, capture_output=True)
        # Return it to the browser as a streamable audio file
        media_type = "audio/webm" if ext == ".webm" else "audio/wav"
        return FileResponse(temp_path, media_type=media_type)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to fetch audio: {str(e)}")

@app.get("/api/marker")
def get_latest_marker():
    try:
        res = subprocess.run(["uvx", "fulcra-api", "file", "list", "/agent/flow-state/templates/"], capture_output=True, text=True)
        lines = [l for l in res.stdout.strip().split('\n') if l]
        if not lines:
            return {"error": "No marker found"}
        # Take the last line which usually is the most recent
        latest_line = lines[-1]
        filename = latest_line.split()[-1]
        file_path = f"/agent/flow-state/templates/{filename}"
        
        # Use file stat to get the real creation date. Note: file stat does not support --json flag yet.
        stat_res = subprocess.run(["uvx", "fulcra-api", "file", "stat", file_path], capture_output=True, text=True)
        created_at = None
        if stat_res.returncode == 0:
            # Parse human-readable output: Uploaded: 2026-08-18T15:04:34.657951Z
            for line in stat_res.stdout.split('\n'):
                if line.startswith("Uploaded: "):
                    created_at = line.split("Uploaded: ")[1].strip()
                    break
                
        return {"file_path": file_path, "created_at": created_at}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/ideas")
def get_ideas():
    try:
        # 1. Fetch the exact UUID of the user's `MusicalIdea` data type dynamically
        type_res = subprocess.run(["uvx", "fulcra-api", "data-type", "list"], capture_output=True, text=True, check=True)
        musical_idea_uuid = None
        for line in type_res.stdout.split('\n'):
            if "MusicalIdea" in line:
                musical_idea_uuid = line.split()[0].strip()
                break
                
        if not musical_idea_uuid:
            return {"error": "MusicalIdea data type not found in this Fulcra account."}
        
        # 2. Fetch tags for label resolution
        tags_res = subprocess.run(["uvx", "fulcra-api", "tag", "list"], capture_output=True, text=True, check=True)
        tags_data = json.loads(tags_res.stdout) if tags_res.stdout.strip() else []
        tag_lookup = {t['id']: t['name'] for t in tags_data}
        
        # 3. Fetch records using the dynamic UUID
        records_res = subprocess.run(["uvx", "fulcra-api", "get-records", f"MomentAnnotation/{musical_idea_uuid}", "30 days"], capture_output=True, text=True)
        if records_res.returncode != 0:
            return {"error": f"Failed to fetch records: {records_res.stderr}"}
        
        ideas_feed = []
        for line in records_res.stdout.strip().split('\n'):
            if not line:
                continue
            r = json.loads(line)
            resolved_tags = [tag_lookup.get(t_id, t_id) for t_id in r.get('tags', [])]
            
            key = None
            bpm = None
            for t in resolved_tags:
                if t.startswith('key:'):
                    key = t.split(':')[1]
                elif t.startswith('bpm:'):
                    bpm = t.split(':')[1]
                    
            note = r.get('note', '')
            file_path = None
            source_file = None
            start_time = 0
            
            if 'Extracted from ' in note:
                source_file = note.split('Extracted from ')[1].split('. ')[0]
            
            if 'File: ' in note:
                file_path = note.split('File: ')[1].strip()
                
            if file_path:
                match = re.search(r'at_(\d+)m_(\d+)s', file_path)
                if match:
                    start_time = int(match.group(1)) * 60 + int(match.group(2))
                
            ideas_feed.append({
                "id": r['id'],
                "recorded_at": r['recorded_at'],
                "key": key,
                "bpm": bpm,
                "all_tags": resolved_tags,
                "file_path": file_path,
                "source_file": source_file,
                "start_time": start_time,
                "note": note
            })
            
        return ideas_feed
    except Exception as e:
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    mode = websocket.query_params.get("mode", "session")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    fd, temp_path = tempfile.mkstemp(suffix=".webm")
    os.close(fd)
    
    try:
        with open(temp_path, "wb") as f:
            while True:
                data = await websocket.receive()
                if "text" in data and data["text"] == "STOP":
                    break
                if "bytes" in data:
                    f.write(data["bytes"])
                    f.flush()
        
        if mode == "marker":
            fulcra_path = f"/agent/flow-state/templates/marker_{timestamp}.webm"
        else:
            fulcra_path = f"/agent/flow-state/sessions/raw/session_{timestamp}.webm"
            
        try:
            subprocess.run(["uvx", "fulcra-api", "file", "upload", temp_path, fulcra_path], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Fulcra upload failed: {e.stderr}")
            await websocket.send_text(f"❌ Upload failed: {e.stderr}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return
        
        if mode == "session":
            await websocket.send_text(f"⏳ Uploaded to Fulcra: {fulcra_path}. Processing DSP in background...")
            
            # Run the worker synchronously inside the WebSocket lifecycle to wait for completion
            # (Note: In a true production app with multiple users, we would use Celery/Redis for this, 
            # but for a local single-tenant prototype, awaiting an asyncio subprocess is perfect).
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "worker/processor.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                await websocket.send_text("✅ DSP Processing Complete! Check Fulcra for your extracted clips.")
            else:
                await websocket.send_text(f"❌ DSP Processing Failed: {stderr.decode()}")
                
        else:
            await websocket.send_text(f"✅ Uploaded marker successfully to Fulcra: {fulcra_path}")

    except WebSocketDisconnect:
        # Give the normal upload block 2 seconds to clean up the temp_path
        # so we don't accidentally salvage a perfectly good upload just because the socket closed.
        await asyncio.sleep(2.0)
        
        # We only salvage if the file wasn't cleanly uploaded via the Stop button logic.
        # If the file still exists here, it means the WebSocket crashed or the browser tab closed unexpectedly.
        if os.path.exists(temp_path):
            print("WebSocket disconnected unexpectedly. Salvaging recording...")
            fulcra_path = f"/agent/flow-state/sessions/raw/salvaged_{timestamp}.webm"
            try:
                subprocess.run(["uvx", "fulcra-api", "file", "upload", temp_path, fulcra_path], check=True, capture_output=True, text=True)
                if mode == "session":
                    subprocess.Popen([sys.executable, "worker/processor.py"])
            except subprocess.CalledProcessError as e:
                print(f"Salvage upload failed: {e.stderr}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)