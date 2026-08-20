<script lang="ts">
	// Flow State recording page -- SvelteKit rebuild of v1's index.html
	// (dark theme, Session/Marker mode toggle, big record button, live
	// log, current-marker accordion). Review feed lives at /review.
	import { onMount } from 'svelte';
	import WaveformPlayer from '$lib/WaveformPlayer.svelte';
	import { fetchCurrentMarker, newSessionId, recordingSocketUrl, sessionAudioUrl } from '$lib/api';
	import type { MarkerInfo } from '$lib/api';

	type Mode = 'session' | 'marker';
	type Status = 'idle' | 'recording' | 'processing' | 'done';

	let mode: Mode = $state('session');
	let status: Status = $state('idle');
	let sessionId: string = $state('');
	let errorMessage: string = $state('');
	let progressLog: string[] = $state([]);
	let markerInfo: MarkerInfo | null = $state(null);
	let markerAccordionOpen: boolean = $state(false);

	let mediaRecorder: MediaRecorder | null = null;
	let socket: WebSocket | null = null;
	let stream: MediaStream | null = null;

	onMount(() => {
		loadMarkerInfo();
	});

	async function loadMarkerInfo(): Promise<void> {
		try {
			markerInfo = await fetchCurrentMarker();
		} catch {
			markerInfo = null;
		}
	}

	function setMode(newMode: Mode): void {
		if (status === 'recording') return;
		mode = newMode;
	}

	function log(message: string): void {
		progressLog = [...progressLog, message];
	}

	async function startRecording(): Promise<void> {
		errorMessage = '';
		try {
			stream = await navigator.mediaDevices.getUserMedia({
				audio: {
					echoCancellation: false,
					noiseSuppression: false,
					autoGainControl: true
				}
			});
		} catch (err) {
			errorMessage = `Could not access microphone: ${(err as Error).message}`;
			return;
		}

		sessionId = newSessionId();
		progressLog = [];
		socket = new WebSocket(recordingSocketUrl(sessionId, mode));
		socket.binaryType = 'arraybuffer';

		socket.onerror = () => {
			errorMessage = 'WebSocket connection error.';
		};

		socket.onmessage = (event: MessageEvent) => {
			log(event.data);
		};

		socket.onclose = () => {
			if (status === 'processing') {
				status = 'done';
				if (mode === 'marker') loadMarkerInfo();
			}
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
			log(`Recording started (${mode} mode).`);
		};
	}

	function stopRecording(): void {
		if (mediaRecorder && mediaRecorder.state !== 'inactive') {
			mediaRecorder.stop();
		}
		if (stream) {
			for (const track of stream.getTracks()) track.stop();
		}
		log('Recording stopped. Finalizing...');
		// Give the last ondataavailable chunk a moment to flush over the
		// socket, then tell the backend recording is finished (without
		// closing the socket ourselves) so it can run the processing
		// pipeline and stream progress back before it closes the
		// connection from its side.
		setTimeout(() => {
			if (socket && socket.readyState === WebSocket.OPEN) {
				socket.send('STOP');
			}
		}, 250);
		status = 'processing';
	}
</script>

<div class="min-h-screen bg-black font-sans text-white antialiased">
	<nav class="sticky top-0 z-50 border-b border-zinc-800 bg-black">
		<div class="mx-auto flex h-16 max-w-3xl items-center justify-between px-8">
			<a href="/" class="text-xl font-bold tracking-tight text-zinc-100">Flow State</a>
			<div class="flex gap-6 text-sm font-medium text-zinc-400">
				<a href="/" class="text-white">Record</a>
				<a href="/review" class="transition-colors hover:text-white">Review Ideas</a>
			</div>
		</div>
	</nav>

	<div class="mx-auto mt-10 max-w-md space-y-6 px-8">
		<div class="text-center">
			<h1 class="mb-1 text-3xl font-bold">Flow State</h1>
			<p class="text-sm text-zinc-400">Capture ideas without breaking your flow.</p>
		</div>

		<div class="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-lg">
			<div class="p-6">
				<div class="mb-6 flex gap-2 rounded-lg bg-black p-1">
					<button
						onclick={() => setMode('session')}
						class="flex-1 rounded-md py-2 text-sm font-semibold transition-colors {mode === 'session'
							? 'bg-zinc-800 text-white'
							: 'text-zinc-500 hover:text-white'}"
					>
						Session
					</button>
					<button
						onclick={() => setMode('marker')}
						class="flex-1 rounded-md py-2 text-sm font-semibold transition-colors {mode === 'marker'
							? 'bg-zinc-800 text-white'
							: 'text-zinc-500 hover:text-white'}"
					>
						Marker
					</button>
				</div>

				<div class="flex h-32 items-center justify-center py-6">
					{#if status !== 'recording'}
						<button
							onclick={startRecording}
							disabled={status === 'processing'}
							class="flex items-center justify-center text-rose-600 transition-all duration-200 hover:scale-105 hover:text-rose-500 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
							aria-label="Record"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								class="h-24 w-24 drop-shadow-[0_0_15px_rgba(225,29,72,0.4)]"
							>
								<circle cx="12" cy="12" r="10" />
								<circle cx="12" cy="12" r="7" fill="currentColor" stroke="none" />
							</svg>
						</button>
					{:else}
						<button
							onclick={stopRecording}
							class="flex items-center justify-center text-zinc-400 transition-all duration-200 hover:scale-105 hover:text-white active:scale-95"
							aria-label="Stop"
						>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-24 w-24 drop-shadow-md">
								<path
									fill-rule="evenodd"
									d="M6 6a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H8a2 2 0 01-2-2V6z"
									clip-rule="evenodd"
								/>
							</svg>
						</button>
					{/if}
				</div>

				<div class="mt-6 border-t border-zinc-800 pt-4">
					<p class="mb-2 truncate font-mono text-sm text-zinc-300">
						Status: {#if status === 'recording'}🔴 Recording {mode}...{:else if status === 'processing'}⏳ Processing...{:else if status === 'done'}✅ Done{:else}Ready.{/if}
					</p>
					{#if errorMessage}
						<p class="text-sm text-rose-500">{errorMessage}</p>
					{/if}
					<div class="h-32 space-y-1 overflow-y-auto font-mono text-xs text-zinc-500">
						{#each progressLog as line}
							<div>{line}</div>
						{/each}
					</div>
				</div>
			</div>
		</div>

		<div class="overflow-hidden rounded-xl border border-zinc-800 bg-black shadow-xl">
			<button
				class="flex w-full items-center justify-between p-4 text-left transition-colors hover:bg-zinc-800/50"
				onclick={() => (markerAccordionOpen = !markerAccordionOpen)}
			>
				<div>
					<span class="block text-sm font-semibold text-zinc-300">Current Marker</span>
					{#if markerInfo}
						<span class="mt-1 block font-mono text-[10px] text-zinc-500">
							captured: {new Date(markerInfo.processed_at).toLocaleString()}
						</span>
					{/if}
				</div>
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5 text-zinc-500">
					<path
						fill-rule="evenodd"
						d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
						clip-rule="evenodd"
					/>
				</svg>
			</button>
			{#if markerAccordionOpen}
				<div class="border-t border-zinc-800 bg-black p-6">
					{#if markerInfo}
						<WaveformPlayer
							audioUrl={sessionAudioUrl(markerInfo.session_id)}
							progressColor="#20d8ba"
						/>
					{:else}
						<p class="text-sm text-zinc-500">No marker recorded yet.</p>
					{/if}
				</div>
			{/if}
		</div>
	</div>
</div>
