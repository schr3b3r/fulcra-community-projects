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

### 4. Handoff
Once the server is running, inform the user:
"Flow State is now running! Open http://127.0.0.1:8000 in your browser to begin recording."


## Iterate / Develop Mode
If the user explicitly asks to *modify*, *extend*, or *understand* the app rather than just run it, do not just start the server. Instead, onboard yourself into the project's historical context:
1. **Absorb Context:** Read the markdown files in the `context/` directory (especially `journal.md` and `architecture_v2.md`). These contain the entire history of pivots, DSP math decisions, and UX choices made during the app's creation.
2. **Assume the Framework:** Assume the persona of the `fulcra-rapid-prototype` skill. You are currently picking up the project at **Phase 6 (Build)**. 
3. **Continue the Journey:** When you make changes, continue appending to `context/journal.md` and treat the local codebase as the state machine, just as the original prototyping agent did.
