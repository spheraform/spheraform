<script lang="ts">
	import { onMount } from 'svelte';

	interface Server {
		id: string;
		name: string;
		base_url: string;
		provider_type: string;
		country: string;
		is_active: boolean;
		last_crawled_at: string | null;
	}

	let servers: Server[] = [];
	let loading = true;
	let error: string | null = null;

	onMount(async () => {
		try {
			const response = await fetch('/api/v1/servers');
			if (!response.ok) throw new Error('Failed to fetch servers');
			servers = await response.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			loading = false;
		}
	});

	async function addServer() {
		const url = prompt('Enter ArcGIS server URL:');
		if (!url) return;

		const name = prompt('Enter server name:');
		if (!name) return;

		const country = prompt('Enter country code (e.g., US, GB):');

		try {
			const response = await fetch('/api/v1/servers', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name,
					base_url: url,
					provider_type: 'arcgis',
					country: country || null
				})
			});

			if (!response.ok) throw new Error('Failed to add server');

			const newServer = await response.json();
			servers = [...servers, newServer];
		} catch (e) {
			alert('Error adding server: ' + (e instanceof Error ? e.message : 'Unknown error'));
		}
	}

	async function crawlServer(serverId: string) {
		try {
			const response = await fetch(`/api/v1/servers/${serverId}/crawl`, {
				method: 'POST'
			});

			if (!response.ok) throw new Error('Failed to crawl server');

			alert('Crawl started! This may take a while.');
		} catch (e) {
			alert('Error crawling server: ' + (e instanceof Error ? e.message : 'Unknown error'));
		}
	}
</script>

<div class="servers-tab">
	<div class="header">
		<h3>Geoservers</h3>
		<button class="add-btn" on:click={addServer}>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<line x1="12" y1="5" x2="12" y2="19"></line>
				<line x1="5" y1="12" x2="19" y2="12"></line>
			</svg>
			Add Server
		</button>
	</div>

	{#if loading}
		<div class="loading">Loading servers...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if servers.length === 0}
		<div class="empty">No servers configured. Click "Add Server" to get started.</div>
	{:else}
		<div class="server-list">
			{#each servers as server}
				<div class="server-card">
					<div class="server-info">
						<h4>{server.name}</h4>
						<p class="url">{server.base_url}</p>
						<div class="meta">
							<span class="badge">{server.provider_type}</span>
							{#if server.country}
								<span class="badge">{server.country}</span>
							{/if}
							{#if !server.is_active}
								<span class="badge inactive">Inactive</span>
							{/if}
						</div>
					</div>
					<button class="crawl-btn" on:click={() => crawlServer(server.id)}>
						Crawl
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.servers-tab {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
	}

	.add-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 16px;
		border: none;
		background: var(--text-primary);
		color: white;
		border-radius: 8px;
		cursor: pointer;
		font-size: 14px;
		transition: opacity 0.2s;
	}

	.add-btn:hover {
		opacity: 0.8;
	}

	.loading,
	.error,
	.empty {
		padding: 24px;
		text-align: center;
		color: var(--text-secondary);
	}

	.error {
		color: #dc2626;
	}

	.server-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.server-card {
		padding: 16px;
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		display: flex;
		gap: 12px;
		align-items: flex-start;
		transition: box-shadow 0.2s;
	}

	.server-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.server-info {
		flex: 1;
		min-width: 0;
	}

	h4 {
		margin: 0 0 4px 0;
		font-size: 16px;
		font-weight: 600;
	}

	.url {
		margin: 0 0 8px 0;
		font-size: 12px;
		color: var(--text-secondary);
		word-break: break-all;
	}

	.meta {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.badge {
		padding: 4px 8px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 4px;
		font-size: 11px;
		text-transform: uppercase;
		font-weight: 500;
	}

	.badge.inactive {
		background: #fee;
		color: #dc2626;
	}

	.crawl-btn {
		padding: 8px 16px;
		border: 1px solid rgba(0, 0, 0, 0.2);
		background: white;
		border-radius: 8px;
		cursor: pointer;
		font-size: 13px;
		transition: all 0.2s;
		white-space: nowrap;
	}

	.crawl-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}
</style>
