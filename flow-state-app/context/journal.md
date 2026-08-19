# Prototyping Journal & Decision Log

## The Goal
Create a "Flow State" audio capture tool for musicians that seamlessly records long jam sessions and allows for hands-free bookmarking of "ideas", storing everything natively in Fulcra.

## The Journey & Pivot History

### 1. The Discord Bot (Dead End)
- **Initial Idea:** Use a Discord bot in a private server to record voice channels.
- **The Blocker:** Discord rolled out "DAVE" (End-to-End Encryption based on MLS). Python libraries (`py-cord`) cannot decrypt the client-side audio stream, resulting in encrypted gibberish and crashing the bot.
- **Decision:** Pivot away from Discord to avoid building complex C++ cryptographic bypasses.

### 2. The Telegram Bot (Dead End)
- **Idea:** Use Telegram's mature voice chat UX.
- **The Blocker:** While the bot could join the room, extracting the raw RTP audio stream in Python required low-level C++ hooks (`ntgcalls`) that were too heavy for a rapid prototype.
- **Decision:** Pivot away from third-party chat apps entirely. We need to own the UX.

### 3. The Custom Web App (The Winner)
- **Idea:** A simple, mobile-friendly web app using the browser's `MediaRecorder` API.
- **Deployment Debate:** Next.js (Vercel) vs. Python FastAPI (Render). 
- **Decision:** Chose Python/FastAPI. Why? Because audio conversion (`.webm` to `.wav`) in the browser via JS is fragile. Python gives us bulletproof `ffmpeg` and native use of the Fulcra Python SDK. We deferred deployment to focus on local execution first.

### 4. Solving Data Loss (The WebSocket Pivot)
- **The Risk:** Standard `MediaRecorder` holds audio in RAM until you hit "Stop". If the browser crashes at minute 45, the session is lost.
- **The Fix:** Implemented WebSocket streaming. The browser chunks audio every 2 seconds and streams it to the FastAPI backend, which flushes it to disk instantly. If the browser crashes, the backend salvages the recording up to the last 2 seconds.

### 5. The UX Pivot (Buttons vs. Audio Markers)
- **The Risk:** Clicking a "Mark Idea" button on a screen ruins the musician's flow state (requires taking hands off the instrument).
- **The Fix:** Resurrected our `librosa` DSP math. We record a template "marker" sound (e.g., a high minor triad). The user just plays the marker during the session. A decoupled backend script scans the 45-minute audio, finds the marker via Normalized MFCC Cross-Correlation, and extracts the 30-second lookback window automatically.

### 6. The FFmpeg Header Bug
- **The Risk:** Transcoding chunked/streamed `.webm` files into `.wav` resulted in missing file headers. Standard audio players played silence.
- **The Fix:** Updated the `ffmpeg` pipeline to aggressively ignore errors, force `pcm_s16le` encoding at `44100Hz`, and completely rebuild the `.wav` headers.

### 7. Entering Build Phase
- **Decision:** Proceeding to scaffold the clean architecture. Separating out concerns into `app/` (FastAPI + HTML frontend) and `worker/` (background FFmpeg/DSP logic) to maintain cleanliness in the codebase and set us up for a future Render deployment.

## Conclusion
We successfully proved the entire pipeline locally. The architecture is decoupled, the raw data is safely preserved in Fulcra instantly, and the compute-heavy DSP/transcoding tasks run asynchronously.\n### 8. Production Scaffolding (Build Phase)\n- **Action:** Moved from monolithic spike script to a clean `app/main.py` and `app/static/index.html`.\n- **Decision:** Kept FastAPI static mounting to serve the frontend easily during local execution.
\n### 9. DSP Worker Consolidation\n- **Action:** Created `worker/processor.py`.\n- **Decision:** Bundled the aggressive FFmpeg transcoding (header fix) and the Librosa normalized cross-correlation into a single standalone pipeline. It dynamically grabs the latest files from Fulcra so it can be run asynchronously anytime.
\n### 10. Automated DSP Processing\n- **Action:** Updated `app/main.py` to automatically spawn `worker/processor.py` via `subprocess.Popen`.\n- **Decision:** Trigger the heavy processing asynchronously immediately after a successful upload (or salvage) so the user never has to run CLI commands manually to get their clips.
\n### 11. Fixing DSP False Positives\n- **Action:** Updated `worker/processor.py` to aggressively penalize the 0.00s false positive and correctly sort file lists chronologically.\n- **Decision:** The Fulcra CLI 'list' command isn't guaranteed to return chronologically sorted strings. Added explicit string sorting to ensure the DSP worker always pulls down the absolute newest session and marker.
\n### 12. FFmpeg Video Stream Bug\n- **Action:** Updated `worker/processor.py` to explicitly pass `-vn` and `-max_muxing_queue_size 1024` to ffmpeg during conversion.\n- **Decision:** Chrome's `MediaRecorder` occasionally injects empty video streams or deeply corrupted packet structures into audio-only WebM blobs. This caused `ffmpeg` to silently crash mid-conversion, leaving empty files. By stripping video and increasing the queue, we ensure perfect audio extraction.
\n### 13. Browser Audio Processing Bug (The "Underwater" Sound)\n- **The Risk:** Recording music/guitar through the browser's `MediaRecorder` sounded like it was "underwater" or heavily gated.\n- **The Fix:** Browsers apply heavy echo cancellation, noise suppression, and auto-gain control by default (optimizing for Zoom calls, which destroys music). Updated the `getUserMedia` constraints in `index.html` to explicitly disable all native processing, ensuring the backend receives the raw, pristine audio feed.
\n### 14. Multiple Markers & Silence Trimming\n- **The Risk:** The algorithm only found the absolute *highest* match (missing other occurrences of the marker), and the extracted clips cut off early because the math aligned with the *silence* before the marker instead of the marker itself.\n- **The Fix:** Replaced `np.argmax` with `scipy.signal.find_peaks` to detect *all* occurrences of a marker in a single session. Used `librosa.effects.trim(top_db=25)` on the marker template to snip off leading silence before the math runs, ensuring the timestamps align perfectly with the actual sound.
\n### 15. Naming Conventions\n- **The Issue:** The exported idea clips were named with raw seconds (e.g., `idea_session_20260818_152301_71s.wav`), which is hard to read when browsing files.\n- **The Fix:** Updated the python processor to translate raw seconds into a human-readable `MMm_SSs` format, resulting in clean filenames like `Idea_20260818_152301_at_01m_11s.wav`.
\n### 16. Retro & Finalizing\n- **Action:** Wrote `retro.md` capturing the successes and the platform bugs we hit.\n- **Decision:** Pausing development of the semantic `MusicalIdea` data types until the `fulcra-api data-type create` multiple-base-type resolution bug is fixed in production.
\n### 17. The Bug That Wasn't\n- **Action:** Upgraded `fulcra-api` CLI from v0.1.38 to v0.1.40.\n- **Decision:** It turns out the "Multiple base data types" bug was already patched by the Fulcra team! Upgrading the CLI instantly fixed the issue, allowing us to successfully create custom data types.
\n### 18. Semantic Data Tagging\n- **Action:** Created a custom Fulcra data type `MusicalIdea` (based on `MomentAnnotation`).\n- **Decision:** Updated the DSP worker to automatically calculate the Key Signature and BPM of extracted ideas using `librosa`. Instead of just storing files, it now pushes structured annotations to Fulcra with semantic tags (e.g. `#key:Am`, `#bpm:120`) so ideas can be queried programmatically later.
\n### 19. The CLI Recording Syntax Bug\n- **The Risk:** Recording a `MomentAnnotation` via `subprocess.run` in Python failed repeatedly with `Error: No input provided`.\n- **The Fix:** The Fulcra CLI expects JSON input via `stdin` for complex types. Patched the Python processor to use `subprocess.run(cmd, shell=True)` and pipe `echo '{}'` directly into the `fulcra-api record` command, which successfully authenticates the semantic tags.
- **Decision 4 (Marker Confidence):** Aiming for realtime visual feedback when a marker is played. It's a great UX win, but we'll treat it as a spike candidate since it bridges the gap between async backend processing and realtime frontend state.
- **Decision 5 (The Review Loop):** The review UX will borrow heavily from professional tools like Samply. We are skipping complex project hierarchies for now to focus purely on navigating ideas via semantic tags (Key/BPM), grouping them logically, and providing excellent in-app playback controls.
### 20. End of V2 Interview Phase
- **Status:** Core UX bones are defined. Moving to V2 Architecture.

### 21. V2 Architecture Phase
- **Decision:** Approved architecture utilizing `wavesurfer.js` for playback, Tailwind for dark-mode UX, and new FastAPI routes for Fulcra data fetching and realtime WebSocket feedback.

### 22. V2 Plan Phase
- **Decision:** Defined 3 technical spikes: 1) Realtime Marker Detection, 2) Fulcra Query Route, 3) Premium Playback UI.

### 23. V2 Prototype Phase - Spike 2 (Fulcra Query)
- **Action:** Skipped Spike 1 due to environmental constraints (need real audio input). Tackled Spike 2.
- **Result:** Wrote `spike2_query.py` to query Fulcra records. Found the `MusicalIdea` data type IDs and resolved the tag UUIDs. 
- **Decision:** The JSON payload generated here is the exact shape we will serve via the FastAPI `/api/ideas` endpoint in the Build phase.

### 24. V2 Prototype Phase - Spike 3 (Playback UI)
- **Action:** Created `prototype/waveform_spike.html` to validate the UI/UX direction.
- **Decision:** The dark mode with rounded waveform bars (`wavesurfer.js`) looks incredibly premium. We will integrate this directly into the final Vue/React component in the Build phase.
- **Status:** Prototype phase complete. Backing up repo to Fulcra.

### 25. Entering V2 Build Phase
- **Action:** Transitioning from Prototype to Build phase.
- **Goal:** Integrate Spike 2 (Fulcra Query) and Spike 3 (Playback UI) into the actual `app/main.py` and `app/static/index.html` codebase.

### 26. V2 Build Phase - Backend Route
- **Action:** Added `GET /api/ideas` to `app/main.py`.
- **Implementation:** Integrated the logic from `spike2_query.py` directly into a FastAPI route, wrapping the `fulcra-api` CLI calls to return the JSON feed of `MusicalIdea` assets.

### 27. V2 Build Phase - Frontend Integration
- **Action:** Rebuilt `app/static/index.html`.
- **Implementation:** Integrated the dark-mode Tailwind UI and `wavesurfer.js` logic from Spike 3. Wrapped the legacy PoC recording controls into a sleek left-hand column, and built a dynamic right-hand column that fetches from `/api/ideas` on load (and after DSP finishes) to dynamically render an asset card for every MusicalIdea found in Fulcra.

### 28. End of V2 Build Phase & Retro
- **Status:** V2 Build is complete. The `/api/audio` route successfully bridges the gap between Fulcra storage and browser-native waveform playback.
- **Outcome:** We have transitioned the Flow State app from a brittle technical spike into a cohesive, dark-mode product prototype with a highly functional Review Feed.
- **Next Steps (Deferred):** The realtime marker detection (WebSocket spike) remains deferred until we have a real acoustic environment to tune the DSP heuristics against.
