import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	// Proxy /api requests to the backend API in production
	if (event.url.pathname.startsWith('/api')) {
		const apiUrl = process.env.API_URL || 'http://localhost:8000';
		const targetUrl = `${apiUrl}${event.url.pathname}${event.url.search}`;

		try {
			const response = await fetch(targetUrl, {
				method: event.request.method,
				headers: event.request.headers,
				body: event.request.method !== 'GET' && event.request.method !== 'HEAD'
					? await event.request.text()
					: undefined
			});

			const headers = new Headers(response.headers);
			const body = await response.arrayBuffer();

			return new Response(body, {
				status: response.status,
				statusText: response.statusText,
				headers
			});
		} catch (error) {
			console.error('API proxy error:', error);
			return new Response(JSON.stringify({ error: 'API request failed' }), {
				status: 502,
				headers: { 'Content-Type': 'application/json' }
			});
		}
	}

	return resolve(event);
};
