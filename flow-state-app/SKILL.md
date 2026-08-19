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
Run `uvx fulcra-api auth status`. 
If the user is not authenticated, instruct them to authenticate first before continuing. Do not proceed until they confirm they are logged in.

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

### 4. Handoff
Once the server is running, inform the user:
"Flow State is now running! Open http://127.0.0.1:8000 in your browser to begin recording."
