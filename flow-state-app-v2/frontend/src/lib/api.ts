// Shared API client helpers for talking to the FastAPI backend. Kept
// separate from route components so the endpoints/types are defined once
// and reused by both the recording page and the review feed.
//
// Requests use relative paths (/api/..., /ws/...) rather than an
// absolute http://localhost:8000 origin, and rely on the Vite dev
// server's proxy (see vite.config.ts) to forward them to the actual
// backend. This means the browser only ever needs to reach the
// SvelteKit dev server's own origin/port -- important when this app is
// accessed remotely (e.g. via port forwarding into a sandbox), where the
// browser has no route to the backend's port directly even though the
// backend and frontend dev server run side by side on the same machine.

export interface MarkerInfo {
	session_id: string;
	processed_at: string;
}

export interface Idea {
	idea_id: string;
	session_id: string;
	marker_timestamp_seconds: number;
	key: string;
	bpm: number;
	file_path: string;
	recorded_at: string;
}

export async function fetchCurrentMarker(): Promise<MarkerInfo | null> {
	const res = await fetch('/api/marker');
	if (!res.ok) throw new Error(`Failed to fetch marker info: ${res.status}`);
	const data = await res.json();
	return data.marker as MarkerInfo | null;
}

export async function fetchIdeas(): Promise<Idea[]> {
	const res = await fetch('/api/ideas');
	if (!res.ok) throw new Error(`Failed to fetch ideas: ${res.status}`);
	const data = await res.json();
	return (data.ideas ?? []) as Idea[];
}

export function sessionAudioUrl(sessionId: string): string {
	return `/api/audio/session/${encodeURIComponent(sessionId)}`;
}

export function ideaAudioUrl(ideaId: string): string {
	return `/api/audio/idea/${encodeURIComponent(ideaId)}`;
}

/** WebSocket origin for the recording connection. Unlike the plain HTTP
 * calls above, this can't go through the Vite proxy the same passive way
 * (the proxy config does forward /ws with ws:true, so this still routes
 * through the dev server) -- built from the current page's own host so
 * it works whether the page was loaded as localhost or a forwarded/
 * remote hostname, rather than hardcoding localhost. */
export function recordingSocketUrl(sessionId: string, mode: 'session' | 'marker'): string {
	const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	const host = typeof window !== 'undefined' ? window.location.host : 'localhost:5173';
	return `${protocol}//${host}/ws/record/${encodeURIComponent(sessionId)}?mode=${mode}`;
}

export function newSessionId(): string {
	return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Group a flat idea list by session_id, preserving each idea's position
 * (extraction order within a session) -- mirrors v1's Review Feed
 * grouping, so each recorded jam session gets its own card. */
export function groupIdeasBySession(ideas: Idea[]): Map<string, Idea[]> {
	const groups = new Map<string, Idea[]>();
	for (const idea of ideas) {
		const existing = groups.get(idea.session_id);
		if (existing) {
			existing.push(idea);
		} else {
			groups.set(idea.session_id, [idea]);
		}
	}
	return groups;
}

export function formatTime(totalSeconds: number): string {
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = Math.floor(totalSeconds % 60);
	return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
