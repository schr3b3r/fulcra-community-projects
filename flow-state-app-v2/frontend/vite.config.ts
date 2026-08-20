import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Backend origin the dev-server proxy forwards to. Hardcoded to the
// standard local dev port; change here if the backend ever runs
// elsewhere.
const BACKEND_ORIGIN = 'http://localhost:8000';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		})
	],
	server: {
		// Proxy API/WebSocket calls to the FastAPI backend through the Vite
		// dev server itself, rather than having the browser call
		// http://localhost:8000 directly. This means only this dev
		// server's port needs to be reachable from wherever the browser
		// actually is (e.g. only one port needs forwarding when accessing
		// this sandbox remotely) -- the backend connection happens
		// server-side, on the same machine the backend is already running
		// on.
		proxy: {
			'/api': {
				target: BACKEND_ORIGIN,
				changeOrigin: true
			},
			'/ws': {
				target: BACKEND_ORIGIN,
				ws: true,
				changeOrigin: true
			}
		}
	}
});

