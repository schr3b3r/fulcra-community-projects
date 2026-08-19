---
name: flow-state-app
description: "Provisions and launches the Flow State audio capture web app locally."
author: schr3b3r
version: 1.0.0
metadata:
  tags: [fulcra, audio, music, dsp, fastapi]
---

# Flow State App Runner

You are tasked with launching the Flow State audio capture web app for the user. 
Flow State is a web app backed by Fulcra that allows musicians to record jam sessions and asynchronously extract semantic "ideas" via an audio marker.

Because this is a locally-hosted web application that relies on the Fulcra API, you must provision the user's environment before starting the server.

## Execution Steps

Follow these steps exactly, in order:

### 1. Verify Fulcra Authentication
Before proceeding, the user must be authenticated with Fulcra. Use the `fulcra-connect` skill by loading its raw instructions: `skill_view(name="https://raw.githubusercontent.com/fulcradynamics/agent-skills/refs/heads/main/skills/fulcra-connect/SKILL.md")`. Follow its instructions to check the user's status and handle the login flow if necessary. Do not proceed until you confirm they are logged in.

### 2. Provision the Fulcra Data Type
The web app requires a custom Fulcra data type to store the extracted ideas.
Execute the setup script from the skill directory in the terminal:
```bash
bash scripts/setup_fulcra.sh
```

### 3. Launch the Server
Execute the launch script in the terminal in the background:
```bash
bash scripts/start_server.sh
```
*Note: On first run, this script automatically creates a local virtual environment (`.venv`) and installs the required dependencies (FastAPI, Uvicorn, and DSP libraries such as Librosa and SciPy). First-time installation may take 30–60 seconds due to audio processing packages.*

### 4. Handoff
Once the server is running, inform the user:
"Flow State is now running! Open http://127.0.0.1:8000 in your browser to begin recording."


## Iterate / Develop Mode
If the user explicitly asks to *modify*, *extend*, or *understand* the app rather than just run it, do not just start the server. Instead, onboard yourself into the project's historical context:
1. **Absorb Context:** Read `CONTEXT.md` in the root of the project. This is a distilled summary of the architecture, tech stack, and key pivots (like why we use WebSockets and how Fulcra replaces a traditional database).
2. **Assume the Framework:** Load the `fulcra-rapid-prototype` skill using `skill_view(name="fulcra-rapid-prototype")` to adopt its exact rules, structure, and persona. You are currently picking up this project at **Phase 6 (Build)** of that pipeline.
3. **Continue the Journey:** Maintain a high-signal approach. You do not need to keep a chronological journal, but if you make major architectural shifts, update `CONTEXT.md` to leave the campsite clean for the next agent.
