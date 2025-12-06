<script lang="ts">
	import { onMount } from 'svelte';
	import ServerForm from '$lib/components/Modals/ServerForm.svelte';
	import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
	import InfoModal from '$lib/components/Modals/InfoModal.svelte';
	import InfoDetailModal from '$lib/components/Modals/InfoDetailModal.svelte';

	interface Server {
		id: string;
		name: string;
		base_url: string;
		provider_type: string;
		country: string;
		is_active: boolean;
		health_status: string | null;
		last_crawled_at: string | null;
		// UI state
		expanded?: boolean;
		loading?: boolean;
		crawling?: boolean;
		datasets?: any[];
	}

	export let sidebarWidth: number = 400;

	let servers: Server[] = [];
	let loading = true;
	let error: string | null = null;

	// Filtering and sorting state
	let filterCountry = '';
	let filterServerType = '';
	let filterHealthStatus = '';
	let sortBy: 'name' | 'country' | '' = '';
	let sortAscending = true;

	// Grid view: activate when sidebar is wider than 600px
	$: useGridView = sidebarWidth > 600;

	// Get unique values for filter dropdowns
	$: countries = [...new Set(servers.map(s => s.country).filter(Boolean))].sort();
	$: serverTypes = [...new Set(servers.map(s => s.provider_type).filter(Boolean))].sort();
	$: healthStatuses = [...new Set(servers.map(s => s.health_status).filter(Boolean))].sort();

	// Filtered and sorted servers
	$: filteredServers = servers
		.filter(s => !filterCountry || s.country === filterCountry)
		.filter(s => !filterServerType || s.provider_type === filterServerType)
		.filter(s => !filterHealthStatus || s.health_status === filterHealthStatus)
		.sort((a, b) => {
			if (!sortBy) return 0;
			const aVal = a[sortBy] || '';
			const bVal = b[sortBy] || '';
			const comparison = aVal.localeCompare(bVal);
			return sortAscending ? comparison : -comparison;
		});

	// Modal state
	let showAddModal = false;
	let showEditModal = false;
	let editInitial: any = null;
	let serverBeingEdited: Server | null = null;

	let showConfirmDelete = false;
	let serverToDelete: Server | null = null;

	let showInfoModal = false;
	let infoMessage = '';

	// Detail modal state
	let showDetailModal = false;
	let detailModalTitle = '';
	let detailModalRows: Array<{ label: string; value: string; link?: boolean }> = [];

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

	function formatExtent(extent: any): string {
		if (!extent || !extent.coordinates) return 'N/A';
		try {
			const coords = extent.coordinates[0];
			if (!coords || coords.length < 2) return 'N/A';
			const [[minX, minY], [maxX, maxY]] = [coords[0], coords[2]];
			return `[${minX.toFixed(2)}, ${minY.toFixed(2)}, ${maxX.toFixed(2)}, ${maxY.toFixed(2)}]`;
		} catch {
			return 'N/A';
		}
	}

	function showServerDetails(server: Server) {
		detailModalTitle = `Server: ${server.name}`;
		detailModalRows = [
			{ label: 'Type', value: server.provider_type },
			{ label: 'Country', value: server.country || 'N/A' },
			{ label: 'URL', value: server.base_url, link: true },
			{ label: 'Datasets', value: String(server.datasets?.length || 0) },
			{ label: 'Status', value: server.health_status || 'Unknown' },
			{ label: 'Last Crawl', value: server.last_crawled_at ? new Date(server.last_crawled_at).toLocaleString() : 'Never' }
		];
		showDetailModal = true;
	}

	function showDatasetDetails(dataset: any) {
		detailModalTitle = `Dataset: ${dataset.name}`;
		detailModalRows = [];

		if (dataset.access_url) {
			detailModalRows.push({ label: 'Access URL', value: dataset.access_url, link: true });
		}
		if (dataset.url) {
			detailModalRows.push({ label: 'URL', value: dataset.url, link: true });
		}
		detailModalRows.push(
			{ label: 'Extent', value: formatExtent(dataset.extent) },
			{ label: 'Features', value: dataset.feature_count?.toLocaleString() || 'N/A' }
		);
		if (dataset.keywords && dataset.keywords.length > 0) {
			detailModalRows.push({ label: 'Keywords', value: dataset.keywords.join(', ') });
		}

		showDetailModal = true;
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

	<!-- Filters and Sorting -->
	<div class="filters">
		<select bind:value={filterCountry} class="filter-select">
			<option value="">All Countries</option>
			{#each countries as country}
				<option value={country}>{country}</option>
			{/each}
		</select>
		<select bind:value={filterServerType} class="filter-select">
			<option value="">All Types</option>
			{#each serverTypes as type}
				<option value={type}>{type}</option>
			{/each}
		</select>
		<select bind:value={filterHealthStatus} class="filter-select">
			<option value="">All Status</option>
			{#each healthStatuses as status}
				<option value={status}>{status}</option>
			{/each}
		</select>
		<select bind:value={sortBy} class="filter-select">
			<option value="">No Sort</option>
			<option value="name">Sort by Name</option>
			<option value="country">Sort by Country</option>
		</select>
		{#if sortBy}
			<button class="sort-direction-btn" on:click={() => sortAscending = !sortAscending} title={sortAscending ? 'Ascending' : 'Descending'}>
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					{#if sortAscending}
						<line x1="12" y1="19" x2="12" y2="5"></line>
						<polyline points="5 12 12 5 19 12"></polyline>
					{:else}
						<line x1="12" y1="5" x2="12" y2="19"></line>
						<polyline points="5 12 12 19 19 12"></polyline>
					{/if}
				</svg>
			</button>
		{/if}
	</div>

	<!-- Modals -->
	<ServerForm open={showAddModal} mode="add" on:save={handleAddSave} on:close={() => showAddModal = false} />
	<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={handleEditSave} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />
	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={handleDeleteConfirm} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />
	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />
	<InfoDetailModal open={showDetailModal} title={detailModalTitle} rows={detailModalRows} on:close={() => showDetailModal = false} />

	{#if loading}
		<div class="loading">Loading servers...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if servers.length === 0}
		<div class="empty">No servers configured. Click "Add Server" to get started.</div>
	{:else}
		<div class="server-list" class:grid-view={useGridView}>
			{#each filteredServers as server}
				<div class="server-card" class:expanded={server.expanded} on:click={() => toggleServer(server)}>
					<div class="server-header">
						<div class="server-info">
							<h4>{server.name}</h4>
							<button class="icon-btn server-info-btn" on:click|stopPropagation={() => showServerDetails(server)} title="View Details">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<circle cx="12" cy="12" r="10"></circle>
									<line x1="12" y1="16" x2="12" y2="12"></line>
									<line x1="12" y1="8" x2="12.01" y2="8"></line>
								</svg>
							</button>
						</div>
						<div class="server-actions">
							<button class="icon-btn edit-btn" on:click|stopPropagation={() => openEdit(server)} title="Edit">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
									<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
								</svg>
							</button>
							<button class="icon-btn crawl-btn" on:click|stopPropagation={() => crawlServer(server.id)} disabled={server.crawling} title={server.crawling ? 'Crawling...' : 'Crawl'}>
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polygon points="5 3 19 12 5 21 5 3"></polygon>
								</svg>
							</button>
							<button class="icon-btn delete-btn" on:click|stopPropagation={() => confirmDelete(server)} title="Delete">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polyline points="3 6 5 6 21 6"></polyline>
									<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
								</svg>
							</button>
						</div>
					</div>

					{#if server.expanded}
						<div class="datasets-section" on:click|stopPropagation>
							{#if server.loading}
								<div class="datasets-loading">Loading datasets...</div>
							{:else if server.datasets && server.datasets.length > 0}
								<div class="dataset-list">
									{#each server.datasets as dataset}
										<div class="dataset-card">
											<div class="dataset-row">
												<span class="dataset-name">{dataset.name}</span>
												{#if dataset.feature_count}
													<span class="badge feature-badge">{dataset.feature_count.toLocaleString()}</span>
												{/if}
												<div class="dataset-actions">
													<button class="icon-btn info-btn" on:click|stopPropagation={() => showDatasetDetails(dataset)} title="View Details">
														<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<circle cx="12" cy="12" r="10"></circle>
															<line x1="12" y1="16" x2="12" y2="12"></line>
															<line x1="12" y1="8" x2="12.01" y2="8"></line>
														</svg>
													</button>
													<button class="icon-btn play-btn" on:click|stopPropagation={(e) => downloadDataset(dataset, e)} title={dataset.is_cached ? 'Download' : 'Fetch & Cache'}>
														<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<polygon points="5 3 19 12 5 21 5 3"></polygon>
														</svg>
													</button>
												</div>
											</div>
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
		overflow: visible;
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
		overflow: visible;
	}

	.server-card {
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		overflow: visible;
		transition: all 0.2s;
		cursor: pointer;
	}

	.server-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		background: rgba(0, 0, 0, 0.01);
	}

	.server-card.expanded {
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
	}

	.server-header {
		padding: 10px 12px;
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.server-info {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 6px;
	}

	h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}


	.badge {
		padding: 2px 6px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 3px;
		font-size: 10px;
		text-transform: uppercase;
		font-weight: 500;
		white-space: nowrap;
	}

	.feature-badge {
		background: rgba(59, 130, 246, 0.1);
		color: #3b82f6;
		font-weight: 600;
	}

	.icon-btn {
		width: 28px;
		height: 28px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.15);
		background: white;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		flex-shrink: 0;
	}

	.icon-btn:hover {
		background: rgba(0, 0, 0, 0.05);
		border-color: rgba(0, 0, 0, 0.25);
	}

	.icon-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.delete-btn {
		border-color: #fca5a5;
		color: #dc2626;
	}

	.delete-btn:hover {
		background: #fee;
		border-color: #dc2626;
	}

	.server-actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		position: relative;
		z-index: 10;
	}

	.datasets-section {
		margin-top: 12px;
		width: 100%;
	}

	.datasets-loading,
	.datasets-empty {
		padding: 12px;
		text-align: center;
		color: var(--text-secondary);
		font-size: 13px;
	}

	.dataset-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.dataset-card {
		background: rgba(0, 0, 0, 0.02);
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-radius: 6px;
		transition: all 0.2s;
	}

	.dataset-card:hover {
		background: rgba(0, 0, 0, 0.04);
		border-color: rgba(0, 0, 0, 0.15);
	}

	.dataset-row {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 8px;
	}

	.dataset-name {
		flex: 1;
		font-size: 12px;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
	}

	.dataset-actions {
		display: flex;
		gap: 4px;
		flex-shrink: 0;
	}


	/* Filters and Sorting */
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-bottom: 16px;
		padding: 0 0 12px 0;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.filter-select {
		flex: 1;
		min-width: 120px;
		padding: 6px 10px;
		border: 1px solid rgba(0, 0, 0, 0.15);
		border-radius: 6px;
		background: white;
		font-size: 12px;
		color: var(--text-primary);
		cursor: pointer;
		transition: all 0.2s;
	}

	.filter-select:hover {
		border-color: rgba(0, 0, 0, 0.25);
	}

	.filter-select:focus {
		outline: none;
		border-color: var(--text-primary);
	}

	.sort-direction-btn {
		width: 32px;
		height: 32px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.15);
		background: white;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
	}

	.sort-direction-btn:hover {
		background: rgba(0, 0, 0, 0.05);
		border-color: rgba(0, 0, 0, 0.25);
	}

	/* Grid View */
	.server-list.grid-view {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 12px;
	}

	.server-list.grid-view .server-card {
		height: fit-content;
	}
</style>
