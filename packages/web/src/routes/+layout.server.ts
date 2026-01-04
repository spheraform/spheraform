export function load() {
	return {
		config: {
			apiUrl: process.env.API_URL || 'http://localhost:8000'
		}
	};
}
