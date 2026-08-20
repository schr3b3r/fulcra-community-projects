# Feature: Recording Frontend

## Status
not_started

## Description
Browser-based UI for musicians to start/stop a recording session, capture
real microphone audio, stream it to the backend (see
`websocket_audio_streaming.md`), and later review/play back extracted
musical ideas.

## Acceptance Criteria
- [ ] A page lets the user start a recording session using the browser's
      microphone (`getUserMedia`), with echo cancellation disabled and
      auto-gain enabled (for cleaner audio capture).
- [ ] Captured audio is chunked and sent to the backend's WebSocket
      endpoint in real time as the session progresses.
- [ ] The user can stop the session cleanly, and the backend confirms the
      full recording was received.
- [ ] A separate review view lists previously extracted musical ideas and
      allows playback of each clip.

## Dependencies
websocket_audio_streaming.md, musical_idea_publishing.md (for the review
view to have anything to list)

## Notes
This is the largest, most user-facing feature and depends on several
backend features being in place first. Likely the last feature to be
picked up, once the backend pipeline (streaming -> detection -> extraction
-> publishing) is proven end-to-end.
