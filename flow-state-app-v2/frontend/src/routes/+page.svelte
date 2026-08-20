<script lang="ts">
	// Minimal end-to-end slice: record -> stream to backend over WebSocket ->
	// land on disk as raw/<session_id>.webm. Deliberately bare-bones (no
	// styling, no review view yet) -- see app/features/recording_frontend.md
	// for the full spec this is a first slice of.

	const BACKEND_HTTP_ORIGIN = 'http://localhost:8000';
	const BACKEND_WS_ORIGIN = 'ws://localhost:8000';

	let status: string = $state('idle');
	let sessionId: string = $state('');
	let errorMessage: string = $state('');

	let mediaRecorder: MediaRecorder | null = null;
	let socket: WebSocket | null = null;
	let stream: MediaStream | null = null;

	function newSessionId(): string {
		return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
	}

	async function startRecording(): Promise<void> {
		errorMessage = '';
		try {
			stream = await navigator.mediaDevices.getUserMedia({
				audio: {
					echoCancellation: false,
					autoGainControl: true
				}
			});
		} catch (err) {
			errorMessage = `Could not access microphone: ${(err as Error).message}`;
			return;
		}

		sessionId = newSessionId();
		socket = new WebSocket(`${BACKEND_WS_ORIGIN}/ws/record/${sessionId}`);
		socket.binaryType = 'arraybuffer';

		socket.onerror = () => {
			errorMessage = 'WebSocket connection error.';
		};

		socket.onopen = () => {
			if (!stream) return;
			mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

			mediaRecorder.ondataavailable = (event: BlobEvent) => {
				if (event.data.size > 0 && socket && socket.readyState === WebSocket.OPEN) {
					socket.send(event.data);
				}
			};

			mediaRecorder.start(2000); // emit a chunk every ~2 seconds
			status = 'recording';
		};
	}

	function stopRecording(): void {
		if (mediaRecorder && mediaRecorder.state !== 'inactive') {
			mediaRecorder.stop();
		}
		if (stream) {
			for (const track of stream.getTracks()) track.stop();
		}
		// Give the last ondataavailable chunk a moment to flush over the
		// socket before closing it.
		setTimeout(() => {
			socket?.close();
		}, 250);
		status = 'stopped';
	}
</script>

<h1>Flow State — Record</h1>

<p>Status: <strong>{status}</strong></p>
{#if sessionId}
	<p>Session ID: <code>{sessionId}</code></p>
{/if}
{#if errorMessage}
	<p style="color: red;">{errorMessage}</p>
{/if}

<button onclick={startRecording} disabled={status === 'recording'}>Record</button>
<button onclick={stopRecording} disabled={status !== 'recording'}>Stop</button>

<p>
	Backend health check: <a href={`${BACKEND_HTTP_ORIGIN}/health`} target="_blank">{BACKEND_HTTP_ORIGIN}/health</a>
</p>
