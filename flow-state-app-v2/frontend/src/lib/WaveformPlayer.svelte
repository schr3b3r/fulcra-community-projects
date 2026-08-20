<script lang="ts">
	// Reusable waveform + play/pause control, backed by wavesurfer.js.
	// Mirrors v1's repeated per-clip wavesurfer wiring (index.html), but as
	// a single reusable Svelte component instead of copy-pasted vanilla JS.
	import { onDestroy, onMount } from 'svelte';
	import WaveSurfer from 'wavesurfer.js';
	import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
	import { formatTime } from '$lib/api';

	interface Region {
		start: number;
		end: number;
		color: string;
	}

	let {
		audioUrl,
		waveColor = '#4f4f4f',
		progressColor = '#e11d48',
		height = 50,
		regions = []
	}: {
		audioUrl: string;
		waveColor?: string;
		progressColor?: string;
		height?: number;
		regions?: Region[];
	} = $props();

	let containerEl: HTMLDivElement;
	let wavesurfer: WaveSurfer | null = null;
	let isReady = $state(false);
	let isPlaying = $state(false);
	let currentTime = $state(0);
	let duration = $state(0);

	onMount(() => {
		const regionsPlugin = RegionsPlugin.create();
		wavesurfer = WaveSurfer.create({
			container: containerEl,
			waveColor,
			progressColor,
			cursorColor: '#ffffff',
			barWidth: 2,
			barGap: 2,
			barRadius: 2,
			height,
			url: audioUrl,
			plugins: regions.length > 0 ? [regionsPlugin] : []
		});

		wavesurfer.on('ready', () => {
			isReady = true;
			duration = wavesurfer?.getDuration() ?? 0;
			for (const region of regions) {
				regionsPlugin.addRegion({
					start: region.start,
					end: region.end,
					color: region.color,
					drag: false,
					resize: false
				});
			}
		});
		wavesurfer.on('audioprocess', () => {
			currentTime = wavesurfer?.getCurrentTime() ?? 0;
		});
		wavesurfer.on('interaction', () => {
			currentTime = wavesurfer?.getCurrentTime() ?? 0;
		});
		wavesurfer.on('play', () => (isPlaying = true));
		wavesurfer.on('pause', () => (isPlaying = false));
		wavesurfer.on('finish', () => (isPlaying = false));
	});

	onDestroy(() => {
		wavesurfer?.destroy();
	});

	function togglePlay(): void {
		if (!isReady || !wavesurfer) return;
		wavesurfer.playPause();
	}
</script>

<div class="flex flex-col gap-2">
	<div bind:this={containerEl} class="cursor-pointer"></div>
	<div class="flex items-center gap-4">
		<button
			onclick={togglePlay}
			disabled={!isReady}
			class="w-20 rounded-full bg-zinc-100 px-4 py-1.5 text-xs font-semibold text-black transition-colors hover:bg-white disabled:opacity-50"
		>
			{isPlaying ? 'Pause' : 'Play'}
		</button>
		<span class="font-mono text-xs text-zinc-500">
			{#if isReady}
				{formatTime(currentTime)} / {formatTime(duration)}
			{:else}
				Loading...
			{/if}
		</span>
	</div>
</div>
