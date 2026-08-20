// Shared API client helpers for talking to the FastAPI backend. Kept
// separate from route components so the endpoints/types are defined once
// and reused by both the recording page and the review feed.

export const BACKEND_HTTP_ORIGIN = 'http://localhost:8000';
export const BACKEND_WS_ORIGIN = 'ws://localhost:8000';

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
	const res = await fetch(`${BACKEND_HTTP_ORIGIN}/api/marker`);
	if (!res.ok) throw new Error(`Failed to fetch marker info: ${res.status}`);
	const data = await res.json();
	return data.marker as MarkerInfo | null;
}

export async function fetchIdeas(): Promise<Idea[]> {
	const res = await fetch(`${BACKEND_HTTP_ORIGIN}/api/ideas`);
	if (!res.ok) throw new Error(`Failed to fetch ideas: ${res.status}`);
	const data = await res.json();
	return (data.ideas ?? []) as Idea[];
}

export function sessionAudioUrl(sessionId: string): string {
	return `${BACKEND_HTTP_ORIGIN}/api/audio/session/${encodeURIComponent(sessionId)}`;
}

export function ideaAudioUrl(ideaId: string): string {
	return `${BACKEND_HTTP_ORIGIN}/api/audio/idea/${encodeURIComponent(ideaId)}`;
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
