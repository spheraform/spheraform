<script lang="ts">
	import { onMount } from 'svelte';
	import ServerForm from '$lib/components/Modals/ServerForm.svelte';
	import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
	import InfoModal from '$lib/components/Modals/InfoModal.svelte';

	interface Server {
		id: string;
		name: string;
		base_url: string;
		provider_type: string;
		country: string;
		is_active: boolean;
		last_crawled_at: string | null;
		// UI state
		expanded?: boolean;
		loading?: boolean;
		crawling?: boolean;
		datasets?: any[];
	}

	let servers: Server[] = [];
	let loading = true;
	let error: string | null = null;

	// Modal state
	let showAddModal = false;
	let showEditModal = false;
	let editInitial: any = null;
	let serverBeingEdited: Server | null = null;

	let showConfirmDelete = false;
	let serverToDelete: Server | null = null;

	let showInfoModal = false;
	let infoMessage = '';

	onMount(async () => {
		try {
			const response = await fetch('/api/v1/servers');
			if (!response.ok) throw new Error('Failed to fetch servers');
			const list = await response.json();
			servers = list.map((s: any) => ({ ...s, expanded: false, loading: false, crawling: false }));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			loading = false;
		}
	});

	function addServer() {
		// Open modal instead of using prompt()
		showAddModal = true;
	}

	async function handleAddSave(e: any) {
		const payload = e.detail || {};
		// Ensure provider_type defaults to arcgis if not provided
		if (!payload.provider_type) payload.provider_type = 'arcgis';
		try {
			const response = await fetch('/api/v1/servers', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (!response.ok) throw new Error('Failed to add server');
			const newServer = await response.json();
			servers = [...servers, newServer];
			infoMessage = 'Server added';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error adding server: ' + (err instanceof Error ? err.message : String(err));
			showInfoModal = true;
		} finally {
			showAddModal = false;
		}
	}

	async function crawlServer(serverId: string) {
		try {
			const response = await fetch(`/api/v1/servers/${serverId}/crawl`, { method: 'POST' });
			if (!response.ok) throw new Error('Failed to crawl server');
			infoMessage = 'Crawl started. This may take a while.';
			showInfoModal = true;
		} catch (e) {
			infoMessage = 'Error crawling server: ' + (e instanceof Error ? e.message : 'Unknown error');
			showInfoModal = true;
		}

    }

		function openEdit(server: Server) {
			serverBeingEdited = server;
			editInitial = { name: server.name, base_url: server.base_url, country: server.country };
			showEditModal = true;
		}

		async function handleEditSave(e: any) {
			if (!serverBeingEdited) return;
			const payload = e.detail || {};
			try {
				const res = await fetch(`/api/v1/servers/${serverBeingEdited.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
				if (!res.ok) throw new Error('Failed to update server');
				const updated = await res.json();
				servers = servers.map(s => s.id === serverBeingEdited!.id ? { ...s, ...updated } : s);
				infoMessage = 'Server updated'; showInfoModal = true;
			} catch (err) {
				infoMessage = 'Error updating server: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
			} finally {
				showEditModal = false; serverBeingEdited = null;
			}
		}

		function confirmDelete(server: Server) {
			serverToDelete = server;
			showConfirmDelete = true;
		}

		async function handleDeleteConfirm() {
			if (!serverToDelete) return;
			try {
				const res = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
				if (!res.ok && res.status !== 204) throw new Error('Failed to delete');
				servers = servers.filter(s => s.id !== serverToDelete!.id);
				infoMessage = 'Server deleted'; showInfoModal = true;
			} catch (err) {
				infoMessage = 'Error deleting server: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
			} finally {
				showConfirmDelete = false; serverToDelete = null;
			}
		}

		async function toggleServer(server: any) {
			if (!server.expanded && !server.datasets) {
				server.loading = true;
				try {
					const res = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
					if (!res.ok) throw new Error('Failed to fetch datasets');
					server.datasets = await res.json();
				} catch (err) {
					infoMessage = 'Error loading datasets: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
				} finally {
					server.loading = false;
				}
			}
			server.expanded = !server.expanded;
			servers = [...servers];
		}

		async function downloadDataset(dataset: any, e?: Event) {
			e && e.stopPropagation();
			try {
				if (dataset.is_cached) {
					const res = await fetch(`/api/v1/download?dataset_ids=${dataset.id}&format=geojson`);
					if (!res.ok) throw new Error('Failed to download file');
					const blob = await res.blob();
					const url = window.URL.createObjectURL(blob);
					const a = document.createElement('a'); a.href = url; a.download = `${dataset.name || 'dataset'}.geojson`; document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
				} else {
					// start download/cache job
					const res = await fetch('/api/v1/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_ids: [dataset.id], format: 'geojson' }) });
					if (!res.ok) throw new Error('Failed to start download job');
					const data = await res.json();
					if (data.download_url) {
						// immediate download available
						window.location.href = data.download_url;
					} else {
						infoMessage = 'Download started. When caching completes, you can download the GeoJSON from cache.';
						showInfoModal = true;
					}
				}
			} catch (err) {
				infoMessage = 'Error downloading dataset: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
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

	<!-- Modals -->
	<ServerForm open={showAddModal} mode="add" on:save={handleAddSave} on:close={() => showAddModal = false} />
	<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={handleEditSave} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />
	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={handleDeleteConfirm} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />
	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />

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
					<div class="server-actions">
						<button class="action-btn" on:click={() => toggleServer(server)}>{server.expanded ? 'Hide' : 'Datasets'}</button>
						<button class="edit-btn" on:click|stopPropagation={() => openEdit(server)}>Edit</button>
						<button class="crawl-btn" on:click|stopPropagation={() => crawlServer(server.id)} disabled={server.crawling}>{server.crawling ? 'Crawling...' : 'Crawl'}</button>
						<button class="delete-btn danger" on:click|stopPropagation={() => confirmDelete(server)}>Delete</button>
					</div>

					{#if server.expanded}
						<div class="datasets-section">
							{#if server.loading}
								<div class="datasets-loading">Loading datasets...</div>
							{:else if server.datasets && server.datasets.length > 0}
								<div class="dataset-list">
									{#each server.datasets as dataset}
										<div class="dataset-card">
											<div class="dataset-info">
												<div class="dataset-name">{dataset.name}</div>
												<div class="dataset-meta">
													{#if dataset.feature_count}
														<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
													{/if}
												</div>
											</div>
											<button class="download-btn" on:click|stopPropagation={(e) => downloadDataset(dataset, e)}>{dataset.is_cached ? 'Download' : 'Fetch & Cache'}</button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="datasets-empty">No datasets. Try crawling the server.</div>
							{/if}
						</div>
					{/if}
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

	.edit-btn {
		padding: 8px 16px;
		border: 1px solid rgba(0, 0, 0, 0.2);
		background: white;
		border-radius: 8px;
		cursor: pointer;
		font-size: 13px;
		transition: all 0.2s;
		white-space: nowrap;
	}

	.edit-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}

	.delete-btn {
		padding: 8px 16px;
		border: 1px solid rgba(248, 37, 37, 0.759);
		background: rgba(238, 128, 128, 0.207);
		border-radius: 8px;
		cursor: pointer;
		font-size: 13px;
		transition: all 0.2s;
		white-space: nowrap;
	}

	.delete-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}
</style>
