<script lang="ts">
	// Review feed -- SvelteKit rebuild of v1's "Review Ideas" panel:
	// published musical ideas grouped by the session they came from, each
	// with its own waveform + Key/BPM tags, plus the full session audio
	// with the marker's lookback window highlighted as a region.
	import { onMount } from 'svelte';
	import WaveformPlayer from '$lib/WaveformPlayer.svelte';
	import {
		fetchIdeas,
		groupIdeasBySession,
		ideaAudioUrl,
		sessionAudioUrl
	} from '$lib/api';
	import type { Idea } from '$lib/api';

	let ideas: Idea[] = $state([]);
	let loading: boolean = $state(true);
	let errorMessage: string = $state('');

	// Cool color ramp per idea within a group, mirroring v1's D3
	// interpolateCool coloring so each idea's waveform accent and its
	// region on the full session waveform match.
	const COOL_RAMP = ['#20d8ba', '#4c9be8', '#7b7bf0', '#a15ce0', '#c93fce'];

	function colorFor(index: number, total: number): string {
		if (total <= 1) return COOL_RAMP[0];
		const t = index / (total - 1);
		const rampIndex = Math.round(t * (COOL_RAMP.length - 1));
		return COOL_RAMP[rampIndex];
	}

	function toRegionColor(hex: string): string {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return `rgba(${r}, ${g}, ${b}, 0.25)`;
	}

	async function loadIdeas(): Promise<void> {
		loading = true;
		errorMessage = '';
		try {
			ideas = await fetchIdeas();
		} catch (err) {
			errorMessage = (err as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadIdeas();
	});

	function sessionDateLabel(groupIdeas: Idea[]): string {
		const first = groupIdeas[0];
		if (!first?.recorded_at) return 'Unknown date';
		const d = new Date(first.recorded_at);
		return d.toLocaleDateString('en-US', {
			weekday: 'long',
			month: 'short',
			day: 'numeric'
		}) + ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
	}
</script>

<div class="min-h-screen bg-black font-sans text-white antialiased">
	<nav class="sticky top-0 z-50 border-b border-zinc-800 bg-black">
		<div class="mx-auto flex h-16 max-w-5xl items-center justify-between px-8">
			<a href="/" class="text-xl font-bold tracking-tight text-zinc-100">Flow State</a>
			<div class="flex gap-6 text-sm font-medium text-zinc-400">
				<a href="/" class="transition-colors hover:text-white">Record</a>
				<a href="/review" class="text-white">Review Ideas</a>
			</div>
		</div>
	</nav>

	<div class="mx-auto mt-10 max-w-5xl px-8">
		<div class="mb-6 flex items-center justify-between">
			<h2 class="text-2xl font-bold">Review Ideas</h2>
			<button onclick={loadIdeas} class="text-sm text-zinc-400 transition-colors hover:text-white">
				&#8635; Refresh
			</button>
		</div>

		{#if loading}
			<div class="flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-black/50 p-12">
				<p class="font-mono text-sm tracking-widest text-zinc-500 uppercase">Fetching ideas...</p>
			</div>
		{:else if errorMessage}
			<p class="text-sm text-rose-500">Error loading ideas: {errorMessage}</p>
		{:else if ideas.length === 0}
			<p class="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
				No ideas recorded yet. Play your marker during a session to capture one!
			</p>
		{:else}
			{#each groupIdeasBySession(ideas) as [sessionId, groupIdeas] (sessionId)}
				<div class="mb-8 overflow-hidden rounded-xl border border-zinc-800 bg-black shadow-xl">
					<div class="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 p-4">
						<div>
							<h3 class="text-lg font-bold">{sessionDateLabel(groupIdeas)}</h3>
							<p class="mt-1 font-mono text-xs text-zinc-500">{sessionId}</p>
						</div>
						<span class="rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-400">
							{groupIdeas.length} idea{groupIdeas.length > 1 ? 's' : ''} extracted
						</span>
					</div>

					<div class="space-y-4 border-b border-zinc-800 bg-zinc-950 p-4">
						{#each groupIdeas as idea, index (idea.idea_id)}
							<div
								class="rounded-xl border-x border-b border-zinc-800 bg-zinc-900 p-4 shadow-sm transition-colors hover:border-zinc-700"
								style="border-top: 4px solid {colorFor(index, groupIdeas.length)};"
							>
								<div class="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
									<h4 class="truncate text-md font-semibold text-zinc-200">{idea.idea_id}</h4>
									<div class="flex shrink-0 gap-2">
										<span class="rounded-full bg-zinc-800 px-2 py-1 font-mono text-[10px] text-zinc-300">
											Key: {idea.key}
										</span>
										<span class="rounded-full bg-zinc-800 px-2 py-1 font-mono text-[10px] text-zinc-300">
											BPM: {idea.bpm}
										</span>
									</div>
								</div>
								<WaveformPlayer
									audioUrl={ideaAudioUrl(idea.idea_id)}
									progressColor={colorFor(index, groupIdeas.length)}
								/>
							</div>
						{/each}
					</div>

					<div class="bg-zinc-900">
						<div class="p-4 font-semibold text-zinc-300">Full Session Audio</div>
						<div class="border-t border-zinc-800 bg-black p-6">
							<WaveformPlayer
								audioUrl={sessionAudioUrl(sessionId)}
								waveColor="#3f3f46"
								progressColor="#71717a"
								height={80}
								regions={groupIdeas.map((idea, index) => ({
									start: Math.max(0, idea.marker_timestamp_seconds - 15),
									end: idea.marker_timestamp_seconds,
									color: toRegionColor(colorFor(index, groupIdeas.length))
								}))}
							/>
						</div>
					</div>
				</div>
			{/each}
		{/if}
	</div>
</div>
