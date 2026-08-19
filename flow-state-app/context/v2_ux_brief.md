# Flow State - V2 UX Foundations Brief

## Goal
Transition the Flow State audio capture tool from a PoC into a cohesive product prototype with solid UX bones.

## Core Interaction Loops (In Progress)

### 1. Onboarding and Session Initiation
- **Marker Check:** On load, the app detects if the user has a stored audio marker in Fulcra.
- **Onboarding:** If no marker exists, the user is intercepted and guided to record their first trigger marker.
- **Start Flow:** Explicit "Start Session" button to begin recording.
### 3. Marker Confidence (Feedback)
- **Realtime Detection:** The app should provide immediate visual feedback when an audio marker is detected during a session.
- **Complexity Note:** We will spike this to see if it's feasible. If realtime DSP (either in-browser or via fast websocket round-trip) is too complex, we will fall back to asynchronous extraction and iterate on this later.

### 4. The Review Loop
- **Samply Inspiration:** Draw from sleek, professional audio apps like Samply for the UI.
- **Grouping & Stacking:** Ideas should be visually grouped or stacked rather than just a flat, messy list.
- **Semantic Navigation:** Users must be able to navigate and filter recordings by Key Signature and BPM (leveraging the tags we push to Fulcra).
- **In-App Playback:** Sleek, accessible playback controls directly in the web app for reviewing ideas instantly.
- **Scope Boundary:** Avoid building complex "Project" hierarchies for now; focus strictly on navigating and playing back the generated ideas.
