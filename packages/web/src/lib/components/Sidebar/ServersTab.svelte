<script lang="ts">
	import { onMount } from 'svelte';
	import ServerForm from '$lib/components/Modals/ServerForm.svelte';
	import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
	import InfoModal from '$lib/components/Modals/InfoModal.svelte';

	type Dataset = {
		id: string;
		name: string;
		description?: string | null;
		access_url?: string;
		updated_at?: string | null;
		is_cached?: boolean;
		cached_at?: string | null;
	};

	type Server = {
		id: string;
		name: string;
		base_url: string;
		provider_type?: string;
		country?: string;
		is_active?: boolean;
		last_crawled_at?: string | null;
		dataset_count?: number;
		datasets?: Dataset[];
		expanded?: boolean;
		loading?: boolean;
		crawling?: boolean;
	};

	let servers: Server[] = [];
	let loading = true;
	let error: string | null = null;
	let searchQuery = '';
	let sortBy: 'name' | 'datasets' | 'crawled' = 'name';

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
		await loadServers();
	});

	async function loadServers() {
		loading = true;
		error = null;
		try {
			const res = await fetch('/api/v1/servers');
			if (!res.ok) throw new Error('Failed to fetch servers');
			const list = await res.json();
			servers = list.map((s: any) => ({ ...s, expanded: false, loading: false, crawling: false }));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	function openAdd() {
		showAddModal = true;
	}

	function openEdit(server: Server) {
		serverBeingEdited = server;
		editInitial = { name: server.name, base_url: server.base_url, country: server.country };
		showEditModal = true;
	}

	function confirmDelete(server: Server) {
		serverToDelete = server;
		showConfirmDelete = true;
	}

	async function performDelete() {
		if (!serverToDelete) return;
		try {
			const res = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
			if (!res.ok && res.status !== 204) throw new Error('Failed to delete');
			servers = servers.filter(s => s.id !== serverToDelete!.id);
			infoMessage = 'Server deleted';
			showInfoModal = true;
		} catch (e) {
			infoMessage = e instanceof Error ? e.message : String(e);
			showInfoModal = true;
		} finally {
			showConfirmDelete = false;
			serverToDelete = null;
		}
	}

	async function toggleServer(server: Server) {
		if (!server.expanded && !server.datasets) {
			server.loading = true;
			try {
				const res = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
				if (!res.ok) throw new Error('Failed to fetch datasets');
				server.datasets = await res.json();
			} catch (e) {
				infoMessage = 'Error loading datasets: ' + (e instanceof Error ? e.message : String(e));
				showInfoModal = true;
			} finally {
				server.loading = false;
			}
		}
		server.expanded = !server.expanded;
		servers = [...servers];
	}

	async function crawlServer(server: Server, e?: Event) {
		e?.stopPropagation();
		if (server.crawling) return;
		server.crawling = true;
		try {
			const res = await fetch(`/api/v1/servers/${server.id}/crawl`, { method: 'POST' });
			if (!res.ok) throw new Error('Crawl failed');
			const result = await res.json();
			infoMessage = `Crawl complete. Discovered: ${result.datasets_discovered || 0}`;
			showInfoModal = true;
			await loadServers();
		} catch (err) {
			infoMessage = err instanceof Error ? err.message : String(err);
			showInfoModal = true;
		} finally {
			server.crawling = false;
			servers = [...servers];
		}
	}

	async function downloadDataset(dataset: Dataset, e?: Event) {
		e?.stopPropagation();
		try {
			if (dataset.is_cached) {
				const res = await fetch(`/api/v1/download/${dataset.id}/file`);
				if (!res.ok) throw new Error('Failed to download file');
				const blob = await res.blob();
				const url = window.URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `${dataset.name || 'dataset'}.geojson`;
				document.body.appendChild(a);
				a.click();
				a.remove();
				window.URL.revokeObjectURL(url);
			} else {
				const res = await fetch('/api/v1/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_ids: [dataset.id], format: 'geojson' }) });
				if (!res.ok) throw new Error('Failed to start download');
				const data = await res.json();
				if (data.download_url) window.location.href = data.download_url;
				else infoMessage = 'Download started';
			}
		} catch (err) {
			infoMessage = err instanceof Error ? err.message : String(err);
			showInfoModal = true;
		}
	}

	$: filteredServers = servers
		.filter(s =>
			s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
			s.base_url.toLowerCase().includes(searchQuery.toLowerCase()) ||
			(s.country && s.country.toLowerCase().includes(searchQuery.toLowerCase()))
		)
		.sort((a, b) => {
			if (sortBy === 'name') return a.name.localeCompare(b.name);
			if (sortBy === 'datasets') return (b.dataset_count || 0) - (a.dataset_count || 0);
			if (sortBy === 'crawled') {
				if (!a.last_crawled_at) return 1;
				if (!b.last_crawled_at) return -1;
				return new Date(b.last_crawled_at).getTime() - new Date(a.last_crawled_at).getTime();
			}
			return 0;
		});
</script>

<div class="servers-tab">
	<div class="header">
		<h3>Servers & Datasets</h3>
		<button class="add-btn" on:click={openAdd}>Add Server</button>
	</div>

	<div class="controls">
		<input type="text" placeholder="Search servers..." bind:value={searchQuery} class="search-input" />
		<select bind:value={sortBy} class="sort-select">
			<option value="name">Sort by Name</option>
			<option value="datasets">Sort by Datasets</option>
			<option value="crawled">Sort by Last Crawled</option>
		</select>
	</div>

	<ServerForm open={showAddModal} mode="add" on:save={async (e) => {
		try {
			const payload = { ...e.detail };
			const res = await fetch('/api/v1/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
			if (!res.ok) throw new Error('Failed to add server');
			const newServer = await res.json();
			servers = [...servers, { ...newServer, expanded: false, loading: false, crawling: false }];
			showAddModal = false;
			infoMessage = 'Server added';
			showInfoModal = true;
		} catch (err) {
			infoMessage = err instanceof Error ? err.message : String(err);
			showInfoModal = true;
		}
	}} on:close={() => showAddModal = false} />

	<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={async (e) => {
		if (!serverBeingEdited) return;
		const id = serverBeingEdited.id;
		try {
			const res = await fetch(`/api/v1/servers/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(e.detail) });
			if (!res.ok) throw new Error('Failed to update server');
			const updated = await res.json();
			servers = servers.map(s => s.id === id ? { ...s, ...updated } : s);
			showEditModal = false;
			serverBeingEdited = null;
			infoMessage = 'Server updated';
			showInfoModal = true;
		} catch (err) {
			infoMessage = err instanceof Error ? err.message : String(err);
			showInfoModal = true;
		}
	}} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />

	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={performDelete} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />

	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />

	{#if loading}
		<div class="loading">Loading servers...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if filteredServers.length === 0}
		<div class="empty">{searchQuery ? 'No servers match your search.' : 'No servers configured. Click "Add Server" to get started.'}</div>
	{:else}
		<div class="server-list">
			{#each filteredServers as server (server.id)}
				<div class="server-card" class:expanded={server.expanded}>
					<div class="server-header" on:click={() => toggleServer(server)}>
						<div class="server-info">
							<h4>{server.name}</h4>
							<p class="url">{server.base_url}</p>
							<div class="meta">
								<span class="badge">{server.provider_type}</span>
								{#if server.country}
									<span class="badge">{server.country}</span>
								{/if}
								<span class="badge datasets">{server.dataset_count || 0} datasets</span>
								{#if server.last_crawled_at}
									<span class="badge crawled">Crawled {new Date(server.last_crawled_at).toLocaleDateString()}</span>
								{/if}
							</div>
						</div>

						<div class="server-actions">
							<button class="edit-btn" on:click|stopPropagation={() => openEdit(server)}>Edit</button>
							<button class="delete-btn" on:click|stopPropagation={() => confirmDelete(server)}>Delete</button>
							<button class="crawl-btn" on:click|stopPropagation={(e) => crawlServer(server, e)} disabled={server.crawling}>{server.crawling ? 'Crawling...' : 'Crawl'}</button>
						</div>
					</div>

					{#if server.expanded}
						<div class="datasets-section">
							{#if server.loading}
								<div class="datasets-loading">Loading datasets...</div>
							{:else if server.datasets && server.datasets.length > 0}
								<div class="dataset-list">
									{#each server.datasets as dataset (dataset.id)}
										<div class="dataset-card">
											<div class="dataset-info">
												<h5>{dataset.name}</h5>
												{#if dataset.description}
													<p class="description">{dataset.description}</p>
												{/if}
												<div class="dataset-meta">
													{#if dataset.feature_count}
														<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
													{/if}
													<div class="info-tooltip">
														<button class="info-btn" aria-label="More info">i</button>
														<div class="tooltip-content">
															<div><strong>URL:</strong> {#if dataset.access_url}<a href={dataset.access_url} target="_blank" rel="noopener noreferrer">{dataset.access_url}</a>{:else}N/A{/if}</div>
															<div><strong>Updated:</strong> {dataset.updated_at ? new Date(dataset.updated_at).toLocaleString() : 'N/A'}</div>
															<div><strong>Features:</strong> {dataset.feature_count ?? 'N/A'}</div>
														</div>
													</div>
													{#if dataset.is_cached}
														<span class="badge cached">Cached</span>
													{:else}
														<span class="badge not-cached">Not Cached</span>
													{/if}
												</div>
											</div>
											<button class="download-btn" on:click|stopPropagation={(e) => downloadDataset(dataset, e)} title={dataset.is_cached ? 'Download cached GeoJSON' : 'Fetch and download GeoJSON'}>
												Download
											</button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="datasets-empty">No datasets available. Try crawling this server first.</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
/* Minimal styles kept intentionally small to avoid large diffs */
.servers-tab { padding: 12px; }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px }
.add-btn { padding:6px 10px }
.controls { display:flex; gap:8px; margin-bottom:8px }
.search-input { flex:1 }
.server-list { display:flex; flex-direction:column; gap:8px }
.server-card { border:1px solid #ddd; padding:8px; border-radius:6px }
.server-header { display:flex; justify-content:space-between; align-items:center }
.server-info h4 { margin:0 }
.dataset-list { margin-top:8px; display:flex; flex-direction:column; gap:6px }
.dataset-card { display:flex; justify-content:space-between; align-items:center; padding:6px; border-radius:4px; background:#fafafa }
.badge { background:#eee; padding:2px 6px; border-radius:4px; margin-right:6px }
.info-tooltip { position:relative }
.tooltip-content { display:none; position:absolute; right:0; top:100%; background:white; border:1px solid #ccc; padding:8px; width:280px; z-index:50 }
.info-tooltip:hover .tooltip-content { display:block }
</style>
<script lang="ts">
  import { onMount } from 'svelte';
  import ServerForm from '$lib/components/Modals/ServerForm.svelte';
  import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
  import InfoModal from '$lib/components/Modals/InfoModal.svelte';

  type Dataset = {
    id: string;
    name: string;
    description?: string | null;
	<script>
		import { onMount } from 'svelte';
		import ServerForm from '$lib/components/Modals/ServerForm.svelte';
		import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
		import InfoModal from '$lib/components/Modals/InfoModal.svelte';

		let servers = [];
		let loading = true;
		let error = null;
		let searchQuery = '';
		let sortBy = 'name';

		let showAddModal = false;
		let showEditModal = false;
		let editInitial = null;
		let serverBeingEdited = null;
		let showConfirmDelete = false;
		let serverToDelete = null;
		let showInfoModal = false;
		let infoMessage = '';

		onMount(async () => {
			await loadServers();
		});

		async function loadServers() {
			loading = true;
			error = null;
			try {
				const res = await fetch('/api/v1/servers');
				if (!res.ok) throw new Error('Failed to fetch servers');
				const list = await res.json();
				servers = list.map(s => ({ ...s, expanded: false, loading: false, crawling: false }));
			} catch (e) {
				error = e.message || String(e);
			} finally {
				loading = false;
			}
		}

		function openAdd() { showAddModal = true; }
		function openEdit(server) { serverBeingEdited = server; editInitial = { name: server.name, base_url: server.base_url, country: server.country }; showEditModal = true; }
		function confirmDelete(server) { serverToDelete = server; showConfirmDelete = true; }

		async function performDelete() {
			if (!serverToDelete) return;
			try {
				const res = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
				if (!res.ok && res.status !== 204) throw new Error('Failed to delete');
				servers = servers.filter(s => s.id !== serverToDelete.id);
				infoMessage = 'Server deleted'; showInfoModal = true;
			} catch (e) {
				infoMessage = e.message || String(e); showInfoModal = true;
			} finally { showConfirmDelete = false; serverToDelete = null; }
		}

		async function toggleServer(server) {
			if (!server.expanded && !server.datasets) {
				server.loading = true;
				try {
					const res = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
					if (!res.ok) throw new Error('Failed to fetch datasets');
					server.datasets = await res.json();
				} catch (e) { infoMessage = e.message || String(e); showInfoModal = true; } finally { server.loading = false; }
			}
			server.expanded = !server.expanded;
			servers = [...servers];
		}

		async function crawlServer(server, e) {
			e && e.stopPropagation();
			if (server.crawling) return;
			server.crawling = true;
			try {
				const res = await fetch(`/api/v1/servers/${server.id}/crawl`, { method: 'POST' });
				if (!res.ok) throw new Error('Crawl failed');
				const result = await res.json();
				infoMessage = `Crawl complete. Discovered: ${result.datasets_discovered || 0}`; showInfoModal = true; await loadServers();
			} catch (err) { infoMessage = err.message || String(err); showInfoModal = true; } finally { server.crawling = false; servers = [...servers]; }
		}

		async function downloadDataset(dataset, e) {
			e && e.stopPropagation();
			try {
				if (dataset.is_cached) {
					const res = await fetch(`/api/v1/download/${dataset.id}/file`);
					if (!res.ok) throw new Error('Failed to download file');
					const blob = await res.blob();
					const url = window.URL.createObjectURL(blob);
					const a = document.createElement('a'); a.href = url; a.download = `${dataset.name || 'dataset'}.geojson`; document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
				} else {
					const res = await fetch('/api/v1/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_ids: [dataset.id], format: 'geojson' }) });
					if (!res.ok) throw new Error('Failed to start download');
					const data = await res.json(); if (data.download_url) window.location.href = data.download_url; else { infoMessage = 'Download started'; showInfoModal = true; }
				}
			} catch (err) { infoMessage = err.message || String(err); showInfoModal = true; }
		}

		$: filteredServers = servers
			.filter(s => (s.name || '').toLowerCase().includes(searchQuery.toLowerCase()) || (s.base_url || '').toLowerCase().includes(searchQuery.toLowerCase()) || (s.country || '').toLowerCase().includes(searchQuery.toLowerCase()))
			.sort((a, b) => {
				if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '');
				if (sortBy === 'datasets') return (b.dataset_count || 0) - (a.dataset_count || 0);
				if (sortBy === 'crawled') {
					if (!a.last_crawled_at) return 1; if (!b.last_crawled_at) return -1; return new Date(b.last_crawled_at).getTime() - new Date(a.last_crawled_at).getTime();
				}
				return 0;
			});
	</script>

	<div class="servers-tab">
		<div class="header">
			<h3>Servers & Datasets</h3>
			<button class="add-btn" on:click={openAdd}>Add Server</button>
		</div>

		<div class="controls">
			<input type="text" placeholder="Search servers..." bind:value={searchQuery} class="search-input" />
			<select bind:value={sortBy} class="sort-select">
				<option value="name">Sort by Name</option>
				<option value="datasets">Sort by Datasets</option>
				<option value="crawled">Sort by Last Crawled</option>
			</select>
		</div>

		<ServerForm open={showAddModal} mode="add" on:save={async (e) => {
			try {
				const payload = { ...e.detail };
				const res = await fetch('/api/v1/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
				if (!res.ok) throw new Error('Failed to add server');
				const newServer = await res.json();
				servers = [...servers, { ...newServer, expanded: false, loading: false, crawling: false }];
				showAddModal = false;
				infoMessage = 'Server added';
				showInfoModal = true;
			} catch (err) {
				infoMessage = err instanceof Error ? err.message : String(err);
				showInfoModal = true;
			}
		}} on:close={() => showAddModal = false} />

		<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={async (e) => {
			if (!serverBeingEdited) return;
			const id = serverBeingEdited.id;
			try {
				const res = await fetch(`/api/v1/servers/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(e.detail) });
				if (!res.ok) throw new Error('Failed to update server');
				const updated = await res.json();
				servers = servers.map(s => s.id === id ? { ...s, ...updated } : s);
				showEditModal = false;
				serverBeingEdited = null;
				infoMessage = 'Server updated';
				showInfoModal = true;
			} catch (err) {
				infoMessage = err instanceof Error ? err.message : String(err);
				showInfoModal = true;
			}
		}} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />

		<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={performDelete} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />

		<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />

		{#if loading}
			<div class="loading">Loading servers...</div>
		{:else if error}
			<div class="error">{error}</div>
		{:else if filteredServers.length === 0}
			<div class="empty">{searchQuery ? 'No servers match your search.' : 'No servers configured. Click "Add Server" to get started.'}</div>
		{:else}
			<div class="server-list">
				{#each filteredServers as server (server.id)}
					<div class="server-card" class:expanded={server.expanded}>
						<div class="server-header" on:click={() => toggleServer(server)}>
							<div class="server-info">
								<h4>{server.name}</h4>
								<p class="url">{server.base_url}</p>
								<div class="meta">
									<span class="badge">{server.provider_type}</span>
									{#if server.country}
										<span class="badge">{server.country}</span>
									{/if}
									<span class="badge datasets">{server.dataset_count || 0} datasets</span>
									{#if server.last_crawled_at}
										<span class="badge crawled">Crawled {new Date(server.last_crawled_at).toLocaleDateString()}</span>
									{/if}
								</div>
							</div>

							<div class="server-actions">
								<button class="edit-btn" on:click|stopPropagation={() => openEdit(server)}>Edit</button>
								<button class="delete-btn" on:click|stopPropagation={() => confirmDelete(server)}>Delete</button>
								<button class="crawl-btn" on:click|stopPropagation={(e) => crawlServer(server, e)} disabled={server.crawling}>{server.crawling ? 'Crawling...' : 'Crawl'}</button>
							</div>
						</div>

						{#if server.expanded}
							<div class="datasets-section">
								{#if server.loading}
									<div class="datasets-loading">Loading datasets...</div>
								{:else if server.datasets && server.datasets.length > 0}
									<div class="dataset-list">
										{#each server.datasets as dataset (dataset.id)}
											<div class="dataset-card">
												<div class="dataset-info">
													<h5>{dataset.name}</h5>
													{#if dataset.description}
														<p class="description">{dataset.description}</p>
													{/if}
													<div class="dataset-meta">
														{#if dataset.feature_count}
															<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
														{/if}
														<div class="info-tooltip">
															<button class="info-btn" aria-label="More info">i</button>
															<div class="tooltip-content">
																<div><strong>URL:</strong> {#if dataset.access_url}<a href={dataset.access_url} target="_blank" rel="noopener noreferrer">{dataset.access_url}</a>{:else}N/A{/if}</div>
																<div><strong>Updated:</strong> {dataset.updated_at ? new Date(dataset.updated_at).toLocaleString() : 'N/A'}</div>
																<div><strong>Features:</strong> {dataset.feature_count ?? 'N/A'}</div>
															</div>
														</div>
														{#if dataset.is_cached}
															<span class="badge cached">Cached</span>
														{:else}
															<span class="badge not-cached">Not Cached</span>
														{/if}
													</div>
												</div>
												<button class="download-btn" on:click|stopPropagation={(e) => downloadDataset(dataset, e)} title={dataset.is_cached ? 'Download cached GeoJSON' : 'Fetch and download GeoJSON'}>
													Download
												</button>
											</div>
										{/each}
									</div>
								{:else}
									<div class="datasets-empty">No datasets available. Try crawling this server first.</div>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<style>
	/* Minimal styles kept intentionally small to avoid large diffs */
	.servers-tab { padding: 12px; }
	.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px }
	.add-btn { padding:6px 10px }
	.controls { display:flex; gap:8px; margin-bottom:8px }
	.search-input { flex:1 }
	.server-list { display:flex; flex-direction:column; gap:8px }
	.server-card { border:1px solid #ddd; padding:8px; border-radius:6px }
	.server-header { display:flex; justify-content:space-between; align-items:center }
	.server-info h4 { margin:0 }
	.dataset-list { margin-top:8px; display:flex; flex-direction:column; gap:6px }
	.dataset-card { display:flex; justify-content:space-between; align-items:center; padding:6px; border-radius:4px; background:#fafafa }
	.badge { background:#eee; padding:2px 6px; border-radius:4px; margin-right:6px }
	.info-tooltip { position:relative }
	.tooltip-content { display:none; position:absolute; right:0; top:100%; background:white; border:1px solid #ccc; padding:8px; width:280px; z-index:50 }
	.info-tooltip:hover .tooltip-content { display:block }
	</style>
    is_active?: boolean;
    access_url?: string;
    updated_at?: string | null;
    is_cached?: boolean;
    cached_at?: string | null;
  };

  type Server = {
    id: string;
    name: string;
    base_url: string;
    provider_type?: string;
    country?: string;
    is_active?: boolean;
    last_crawled_at?: string | null;
    dataset_count?: number;
    datasets?: Dataset[];
    expanded?: boolean;
    loading?: boolean;
    crawling?: boolean;
  };

  let servers: Server[] = [];
  let loading = true;
  let error: string | null = null;
  let searchQuery = '';
  let sortBy: 'name' | 'datasets' | 'crawled' = 'name';

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
    await loadServers();
  });

  async function loadServers() {
    loading = true;
    error = null;
    try {
      const res = await fetch('/api/v1/servers');
      if (!res.ok) throw new Error('Failed to fetch servers');
      const list = await res.json();
      servers = list.map((s: any) => ({ ...s, expanded: false, loading: false, crawling: false }));
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function openAdd() {
    showAddModal = true;
  }

  function openEdit(server: Server) {
    serverBeingEdited = server;
    editInitial = { name: server.name, base_url: server.base_url, country: server.country };
    showEditModal = true;
  }

  function confirmDelete(server: Server) {
    serverToDelete = server;
    showConfirmDelete = true;
  }

  async function performDelete() {
    if (!serverToDelete) return;
    try {
      const res = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 204) throw new Error('Failed to delete');
      servers = servers.filter(s => s.id !== serverToDelete!.id);
      infoMessage = 'Server deleted';
      showInfoModal = true;
    } catch (e) {
      infoMessage = e instanceof Error ? e.message : String(e);
      showInfoModal = true;
    } finally {
      showConfirmDelete = false;
      serverToDelete = null;
    }
  }

  async function toggleServer(server: Server) {
    if (!server.expanded && !server.datasets) {
      server.loading = true;
      try {
        const res = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
        if (!res.ok) throw new Error('Failed to fetch datasets');
        server.datasets = await res.json();
      } catch (e) {
        infoMessage = 'Error loading datasets: ' + (e instanceof Error ? e.message : String(e));
        showInfoModal = true;
      } finally {
        server.loading = false;
      }
    }
    server.expanded = !server.expanded;
    servers = [...servers];
  }

  async function crawlServer(server: Server, e?: Event) {
    e?.stopPropagation();
    if (server.crawling) return;
    server.crawling = true;
    try {
      const res = await fetch(`/api/v1/servers/${server.id}/crawl`, { method: 'POST' });
      if (!res.ok) throw new Error('Crawl failed');
      const result = await res.json();
      infoMessage = `Crawl complete. Discovered: ${result.datasets_discovered || 0}`;
      showInfoModal = true;
      await loadServers();
    } catch (err) {
      infoMessage = err instanceof Error ? err.message : String(err);
      showInfoModal = true;
    } finally {
      server.crawling = false;
      servers = [...servers];
    }
  }

  async function downloadDataset(dataset: Dataset, e?: Event) {
    e?.stopPropagation();
    try {
      // If cached, retrieve file endpoint; otherwise create download job
      if (dataset.is_cached) {
        const res = await fetch(`/api/v1/download/${dataset.id}/file`);
        if (!res.ok) throw new Error('Failed to download file');
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${dataset.name || 'dataset'}.geojson`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        const res = await fetch('/api/v1/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_ids: [dataset.id], format: 'geojson' }) });
        if (!res.ok) throw new Error('Failed to start download');
        const data = await res.json();
        if (data.download_url) window.location.href = data.download_url;
        else infoMessage = 'Download started';
      }
    } catch (err) {
      infoMessage = err instanceof Error ? err.message : String(err);
      showInfoModal = true;
    }
  }

  $: filteredServers = servers
    .filter(s =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.base_url.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.country && s.country.toLowerCase().includes(searchQuery.toLowerCase()))
    )
    .sort((a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'datasets') return (b.dataset_count || 0) - (a.dataset_count || 0);
      if (sortBy === 'crawled') {
        if (!a.last_crawled_at) return 1;
        if (!b.last_crawled_at) return -1;
        return new Date(b.last_crawled_at).getTime() - new Date(a.last_crawled_at).getTime();
      }
      return 0;
    });
</script>

<div class="servers-tab">
  <div class="header">
    <h3>Servers & Datasets</h3>
    <button class="add-btn" on:click={openAdd}>Add Server</button>
  </div>

  <div class="controls">
    <input type="text" placeholder="Search servers..." bind:value={searchQuery} class="search-input" />
    <select bind:value={sortBy} class="sort-select">
      <option value="name">Sort by Name</option>
      <option value="datasets">Sort by Datasets</option>
      <option value="crawled">Sort by Last Crawled</option>
    </select>
  </div>

  <ServerForm open={showAddModal} mode="add" on:save={async (e) => {
    try {
      const payload = { ...e.detail };
      const res = await fetch('/api/v1/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) throw new Error('Failed to add server');
      const newServer = await res.json();
      servers = [...servers, { ...newServer, expanded: false, loading: false, crawling: false }];
      showAddModal = false;
      infoMessage = 'Server added';
      showInfoModal = true;
    } catch (err) {
      infoMessage = err instanceof Error ? err.message : String(err);
      showInfoModal = true;
    }
  }} on:close={() => showAddModal = false} />

  <ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={async (e) => {
    if (!serverBeingEdited) return;
    const id = serverBeingEdited.id;
    try {
      const res = await fetch(`/api/v1/servers/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(e.detail) });
      if (!res.ok) throw new Error('Failed to update server');
      const updated = await res.json();
      servers = servers.map(s => s.id === id ? { ...s, ...updated } : s);
      showEditModal = false;
      serverBeingEdited = null;
      infoMessage = 'Server updated';
      showInfoModal = true;
    } catch (err) {
      infoMessage = err instanceof Error ? err.message : String(err);
      showInfoModal = true;
    }
  }} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />

  <ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={performDelete} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />

  <InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />

  {#if loading}
    <div class="loading">Loading servers...</div>
  {:else if error}
    <div class="error">{error}</div>
  {:else if filteredServers.length === 0}
    <div class="empty">{searchQuery ? 'No servers match your search.' : 'No servers configured. Click "Add Server" to get started.'}</div>
  {:else}
    <div class="server-list">
      {#each filteredServers as server (server.id)}
        <div class="server-card" class:expanded={server.expanded}>
          <div class="server-header" on:click={() => toggleServer(server)}>
            <div class="server-info">
              <h4>{server.name}</h4>
              <p class="url">{server.base_url}</p>
              <div class="meta">
                <span class="badge">{server.provider_type}</span>
                {#if server.country}
                  <span class="badge">{server.country}</span>
                {/if}
                <span class="badge datasets">{server.dataset_count || 0} datasets</span>
                {#if server.last_crawled_at}
                  <span class="badge crawled">Crawled {new Date(server.last_crawled_at).toLocaleDateString()}</span>
                {/if}
              </div>
            </div>

            <div class="server-actions">
              <button class="edit-btn" on:click|stopPropagation={() => openEdit(server)}>Edit</button>
              <button class="delete-btn" on:click|stopPropagation={() => confirmDelete(server)}>Delete</button>
              <button class="crawl-btn" on:click|stopPropagation={(e) => crawlServer(server, e)} disabled={server.crawling}>{server.crawling ? 'Crawling...' : 'Crawl'}</button>
            </div>
          </div>

          {#if server.expanded}
            <div class="datasets-section">
              {#if server.loading}
                <div class="datasets-loading">Loading datasets...</div>
              {:else if server.datasets && server.datasets.length > 0}
                <div class="dataset-list">
                  {#each server.datasets as dataset (dataset.id)}
                    <div class="dataset-card">
                      <div class="dataset-info">
                        <h5>{dataset.name}</h5>
                        {#if dataset.description}
                          <p class="description">{dataset.description}</p>
                        {/if}
                        <div class="dataset-meta">
                          {#if dataset.feature_count}
                            <span class="badge">{dataset.feature_count.toLocaleString()} features</span>
                          {/if}
                          <div class="info-tooltip">
                            <button class="info-btn" aria-label="More info">i</button>
                            <div class="tooltip-content">
                              <div><strong>URL:</strong> {#if dataset.access_url}<a href={dataset.access_url} target="_blank" rel="noopener noreferrer">{dataset.access_url}</a>{:else}N/A{/if}</div>
                              <div><strong>Updated:</strong> {dataset.updated_at ? new Date(dataset.updated_at).toLocaleString() : 'N/A'}</div>
                              <div><strong>Features:</strong> {dataset.feature_count ?? 'N/A'}</div>
                            </div>
                          </div>
                          {#if dataset.is_cached}
                            <span class="badge cached">Cached</span>
                          {:else}
                            <span class="badge not-cached">Not Cached</span>
                          {/if}
                        </div>
                      </div>
                      <button class="download-btn" on:click|stopPropagation={(e) => downloadDataset(dataset, e)} title={dataset.is_cached ? 'Download cached GeoJSON' : 'Fetch and download GeoJSON'}>
                        Download
                      </button>
                    </div>
                  {/each}
                </div>
              {:else}
                <div class="datasets-empty">No datasets available. Try crawling this server first.</div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
/* Minimal styles kept intentionally small to avoid large diffs */
.servers-tab { padding: 12px; }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px }
.add-btn { padding:6px 10px }
.controls { display:flex; gap:8px; margin-bottom:8px }
.search-input { flex:1 }
.server-list { display:flex; flex-direction:column; gap:8px }
.server-card { border:1px solid #ddd; padding:8px; border-radius:6px }
.server-header { display:flex; justify-content:space-between; align-items:center }
.server-info h4 { margin:0 }
.dataset-list { margin-top:8px; display:flex; flex-direction:column; gap:6px }
.dataset-card { display:flex; justify-content:space-between; align-items:center; padding:6px; border-radius:4px; background:#fafafa }
.badge { background:#eee; padding:2px 6px; border-radius:4px; margin-right:6px }
.info-tooltip { position:relative }
.tooltip-content { display:none; position:absolute; right:0; top:100%; background:white; border:1px solid #ccc; padding:8px; width:280px; z-index:50 }
.info-tooltip:hover .tooltip-content { display:block }
</style>

	let serverToDelete: Server | null = null;
	let showInfoModal = false;
	let infoMessage = '';

	function addServer() {
		showAddModal = true;
	}

	async function toggleServer(server: Server) {
		if (!server.expanded && !server.datasets) {
			// Load datasets for this server
			server.loading = true;
			servers = [...servers];

			try {
				const response = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
				if (!response.ok) throw new Error('Failed to fetch datasets');
				server.datasets = await response.json();
			} catch (e) {
				alert('Error loading datasets: ' + (e instanceof Error ? e.message : 'Unknown error'));
			} finally {
				server.loading = false;
			}
		}

		server.expanded = !server.expanded;
		servers = [...servers];
	}

	function editServer(server: Server) {
		serverBeingEdited = server;
		editInitial = { name: server.name, base_url: server.base_url, country: server.country };
		showEditModal = true;
	}

	function deleteServer(server: Server) {
		serverToDelete = server;
		showConfirmDelete = true;
	}

	async function performDelete() {
		if (!serverToDelete) return;
		try {
			const response = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
			if (!response.ok && response.status !== 204) throw new Error('Failed to delete server');
			servers = servers.filter(s => s.id !== serverToDelete!.id);
			infoMessage = 'Server deleted';
			showInfoModal = true;
		} catch (e) {
			infoMessage = 'Error deleting server: ' + (e instanceof Error ? e.message : 'Unknown error');
			showInfoModal = true;
		} finally {
			showConfirmDelete = false;
			serverToDelete = null;
		}
	}

	async function crawlServer(server: Server, event: Event) {
		event.stopPropagation();

		if (server.crawling) return;

		server.crawling = true;
		servers = [...servers];

		try {
			const response = await fetch(`/api/v1/servers/${server.id}/crawl`, {
				method: 'POST'
			});

			if (!response.ok) throw new Error('Failed to crawl server');

			const result = await response.json();
			infoMessage = `Crawl complete!\n\nDatasets discovered: ${result.datasets_discovered}\nNew datasets: ${result.datasets_new}\nUpdated: ${result.datasets_updated}\nDuration: ${result.crawl_duration_seconds.toFixed(1)}s`;
			showInfoModal = true;

			// Reload server data to get updated dataset count
			await loadServers();

			// If this server was expanded, reload its datasets
			if (server.expanded) {
				const updatedServer = servers.find(s => s.id === server.id);
				if (updatedServer) {
					updatedServer.loading = true;
					servers = [...servers];

							const datasetsResponse = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
					if (datasetsResponse.ok) {
						updatedServer.datasets = await datasetsResponse.json();
					}
					updatedServer.loading = false;
					servers = [...servers];
		<input
			type="text"
			placeholder="Search servers..."
			bind:value={searchQuery}
			class="search-input"
		/>
		<select bind:value={sortBy} class="sort-select">
			<option value="name">Sort by Name</option>
			<option value="datasets">Sort by Datasets</option>
			<option value="crawled">Sort by Last Crawled</option>
		</select>
	</div>

	<!-- Modals -->
	<ServerForm open={showAddModal} mode="add" on:save={async (e) => {
		const payload = { ...e.detail, provider_type: 'arcgis' };
		try {
			const response = await fetch('/api/v1/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
			if (!response.ok) throw new Error('Failed to add server');
			const newServer = await response.json();
			servers = [...servers, { ...newServer, expanded: false, loading: false, crawling: false }];
			showAddModal = false;
			infoMessage = 'Server added';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error adding server: ' + (err instanceof Error ? err.message : 'Unknown error');
			showInfoModal = true;
		}
	}} on:close={() => showAddModal = false} />

	<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={async (e) => {
		if (!serverBeingEdited) return;
		const payload = e.detail;
		try {
			const response = await fetch(`/api/v1/servers/${serverBeingEdited.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
			if (!response.ok) throw new Error('Failed to update server');
			const updated = await response.json();
			servers = servers.map(s => s.id === serverBeingEdited!.id ? { ...s, ...updated } : s);
			showEditModal = false;
			infoMessage = 'Server updated';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error updating server: ' + (err instanceof Error ? err.message : 'Unknown error');
			showInfoModal = true;
		}
	}} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />

	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={performDelete} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />

	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />
		if (!response.ok) {
			const errorData = await response.json();
			throw new Error(errorData.detail || 'Failed to download dataset');
		}

		const blob = await response.blob();
		const url = window.URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${dataset.name.replace(/[^a-zA-Z0-9]/g, '_')}.geojson`;
		document.body.appendChild(a);
		a.click();
		window.URL.revokeObjectURL(url);
		document.body.removeChild(a);
	}

	async function fetchAndDownloadDataset(dataset: Dataset) {
		// Create download job
		const response = await fetch('/api/v1/download', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				dataset_ids: [dataset.id],
				format: 'geojson'
			})
		});

		if (!response.ok) {
			throw new Error('Failed to create download job');
		}

		const result = await response.json();

		// If job_id is returned, poll for completion
		if (result.job_id) {
			await pollJobAndDownload(dataset, result.job_id);
		} else if (result.download_url) {
			// Direct download available
			window.location.href = result.download_url;
		}
	}

	async function pollJobAndDownload(dataset: Dataset, jobId: string) {
		const maxAttempts = 60; // 5 minutes max
		let attempts = 0;

		while (attempts < maxAttempts) {
			const response = await fetch(`/api/v1/download/jobs/${jobId}`);
			if (!response.ok) {
				throw new Error('Failed to check job status');
			}

			const job = await response.json();

			if (job.status === 'completed') {
				// Dataset is now cached, download it
				dataset.is_cached = true;
				await downloadCachedDataset(dataset);
				return;
			} else if (job.status === 'failed') {
				throw new Error(job.error || 'Download job failed');
			}

			// Wait 5 seconds before next poll
			await new Promise(resolve => setTimeout(resolve, 5000));
			attempts++;
		}

		throw new Error('Download timeout - please try again');
	}

	$: filteredServers = servers
		.filter(s =>
			s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
			s.base_url.toLowerCase().includes(searchQuery.toLowerCase()) ||
			(s.country && s.country.toLowerCase().includes(searchQuery.toLowerCase()))
		)
		.sort((a, b) => {
			if (sortBy === 'name') return a.name.localeCompare(b.name);
			if (sortBy === 'datasets') return (b.dataset_count || 0) - (a.dataset_count || 0);
			if (sortBy === 'crawled') {
				if (!a.last_crawled_at) return 1;
				if (!b.last_crawled_at) return -1;
				return new Date(b.last_crawled_at).getTime() - new Date(a.last_crawled_at).getTime();
			}
			return 0;
		});
</script>

<div class="servers-tab">
	<div class="header">
		<h3>Servers & Datasets</h3>
		<button class="add-btn" on:click={addServer}>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<line x1="12" y1="5" x2="12" y2="19"></line>
				<line x1="5" y1="12" x2="19" y2="12"></line>
			</svg>
			Add Server
		</button>
	</div>

	<div class="controls">
		<input
			type="text"
			placeholder="Search servers..."

	<!-- Modals -->
		<ServerForm open={showAddModal} mode="add" on:save={async (e) => {
		const payload = { ...e.detail, provider_type: 'arcgis' };
		try {
			const response = await fetch('/api/v1/servers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
			if (!response.ok) throw new Error('Failed to add server');
			const newServer = await response.json();
			servers = [...servers, { ...newServer, expanded: false, loading: false, crawling: false }];
			showAddModal = false;
			infoMessage = 'Server added';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error adding server: ' + (err instanceof Error ? err.message : 'Unknown error');
			showInfoModal = true;
		}
	}} on:close={() => showAddModal = false} />

		<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={async (e) => {
		if (!serverBeingEdited) return;
		const payload = e.detail;
		try {
			const response = await fetch(`/api/v1/servers/${serverBeingEdited.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
			if (!response.ok) throw new Error('Failed to update server');
			const updated = await response.json();
			servers = servers.map(s => s.id === serverBeingEdited!.id ? { ...s, ...updated } : s);
			showEditModal = false;
			infoMessage = 'Server updated';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error updating server: ' + (err instanceof Error ? err.message : 'Unknown error');
			showInfoModal = true;
		}
	}} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />

	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={performDelete} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />

	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />

</div>
			class="search-input"
		/>
		<select bind:value={sortBy} class="sort-select">
			<option value="name">Sort by Name</option>
			<option value="datasets">Sort by Datasets</option>
			<option value="crawled">Sort by Last Crawled</option>
		</select>
	</div>

	{#if loading}
		<div class="loading">Loading servers...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if filteredServers.length === 0}
		<div class="empty">
			{searchQuery ? 'No servers match your search.' : 'No servers configured. Click "Add Server" to get started.'}
		</div>
	{:else}
		<div class="server-list">
			{#each filteredServers as server (server.id)}
				<div class="server-card" class:expanded={server.expanded}>
					<div class="server-header" on:click={() => toggleServer(server)}>
						<div class="expand-icon">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="9 18 15 12 9 6"></polyline>
							</svg>
						</div>
						<div class="server-info">
							<h4>{server.name}</h4>
							<p class="url">{server.base_url}</p>
							<div class="meta">
								<span class="badge">{server.provider_type}</span>
								{#if server.country}
									<span class="badge">{server.country}</span>
								{/if}
								<span class="badge datasets">{server.dataset_count || 0} datasets</span>
								{#if !server.is_active}
									<span class="badge inactive">Inactive</span>
								{/if}
								{#if server.last_crawled_at}
									<span class="badge crawled">
										Crawled {new Date(server.last_crawled_at).toLocaleDateString()}
									</span>
								{/if}
							</div>
						</div>
						<div class="server-actions">
							<button class="edit-btn" on:click|stopPropagation={() => editServer(server)}>Edit</button>
							<button class="delete-btn" on:click|stopPropagation={() => deleteServer(server)}>Delete</button>
						</div>
						<button
							class="crawl-btn"
							class:crawling={server.crawling}
							on:click={(e) => crawlServer(server, e)}
							disabled={server.crawling}
						>
							{server.crawling ? 'Crawling...' : 'Crawl'}
						</button>
					</div>

					{#if server.expanded}
						<div class="datasets-section">
							{#if server.loading}
								<div class="datasets-loading">Loading datasets...</div>
							{:else if server.datasets && server.datasets.length > 0}
								<div class="dataset-list">
									{#each server.datasets as dataset (dataset.id)}
										<div class="dataset-card">
											<div class="dataset-info">
												<h5>{dataset.name}</h5>
												{#if dataset.description}
													<p class="description">{dataset.description}</p>
												{/if}
												<div class="dataset-meta">
													{#if dataset.feature_count}
														<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
													{/if}
													<!-- Info tooltip -->
													<div class="info-tooltip">
														<button class="info-btn" aria-label="More info">i</button>
														<div class="tooltip-content">
															<div><strong>URL:</strong> <a href="{dataset.access_url}" target="_blank" rel="noopener noreferrer">{dataset.access_url}</a></div>
															<div><strong>Updated:</strong> {dataset.updated_at ? new Date(dataset.updated_at).toLocaleString() : 'N/A'}</div>
															<div><strong>Features:</strong> {dataset.feature_count ?? 'N/A'}</div>
														</div>
													</div>
													{#if dataset.is_cached}
														<span class="badge cached">Cached</span>
													{:else}
														<span class="badge not-cached">Not Cached</span>
													{/if}
													{#if !dataset.is_active}
														<span class="badge inactive">Inactive</span>
													{/if}
												</div>
											</div>
											<button
												class="download-btn"
												class:downloading={dataset.downloading}
												on:click={(e) => downloadDataset(dataset, e)}
												title={dataset.is_cached ? 'Download cached GeoJSON' : 'Fetch and download GeoJSON'}
												disabled={dataset.downloading}
											>
												{#if dataset.downloading}
													<svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<circle cx="12" cy="12" r="10"></circle>
													</svg>
												{:else}
													<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
														<polyline points="7 10 12 15 17 10"></polyline>
														<line x1="12" y1="15" x2="12" y2="3"></line>
													</svg>
												{/if}
											</button>
										</div>
									{/each}
								</div>
							{:else}
								<div class="datasets-empty">No datasets available. Try crawling this server first.</div>
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

	.controls {
		display: flex;
		gap: 8px;
	}

	.search-input {
		flex: 1;
		padding: 8px 12px;
		border: 1px solid rgba(0, 0, 0, 0.2);
		border-radius: 8px;
		font-size: 14px;
	}

	.sort-select {
		padding: 8px 12px;
		border: 1px solid rgba(0, 0, 0, 0.2);
		border-radius: 8px;
		font-size: 14px;
		background: white;
		cursor: pointer;
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
		gap: 8px;
	}

	.server-card {
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		overflow: hidden;
		transition: box-shadow 0.2s;
	}

	.server-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.server-card.expanded {
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
	}

	.server-header {
		padding: 16px;
		display: flex;
		gap: 12px;
		align-items: flex-start;
		cursor: pointer;
		user-select: none;
	}

	.expand-icon {
		width: 20px;
		height: 20px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		margin-top: 2px;
		transition: transform 0.2s;
	}

	.server-card.expanded .expand-icon {
		transform: rotate(90deg);
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

	.badge.datasets {
		background: rgba(59, 130, 246, 0.1);
		color: #2563eb;
	}

	.badge.crawled {
		background: rgba(34, 197, 94, 0.1);
		color: #16a34a;
		text-transform: none;
	}

	.badge.inactive {
		background: #fee;
		color: #dc2626;
	}

	.badge.cached {
		background: rgba(34, 197, 94, 0.1);
		color: #16a34a;
	}

	.badge.not-cached {
		background: rgba(251, 191, 36, 0.1);
		color: #d97706;
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
		flex-shrink: 0;
	}

	.crawl-btn:hover:not(:disabled) {
		background: rgba(0, 0, 0, 0.05);
	}

	.crawl-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.crawl-btn.crawling {
		animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
	}

	.server-actions {
		display: flex;
		gap: 8px;
		margin-right: 8px;
	}

	.edit-btn, .delete-btn {
		padding: 6px 10px;
		border-radius: 6px;
		border: 1px solid rgba(0,0,0,0.12);
		background: white;
		cursor: pointer;
		font-size: 13px;
	}

	.delete-btn {
		background: #fff5f5;
		border-color: rgba(220,38,38,0.12);
		color: #dc2626;
	}

	@keyframes pulse {
		0%, 100% {
			opacity: 1;
		}
		50% {
			opacity: 0.5;
		}
	}

	.datasets-section {
		border-top: 1px solid rgba(0, 0, 0, 0.1);
		background: rgba(0, 0, 0, 0.02);
		padding: 16px;
	}

	.datasets-loading,
	.datasets-empty {
		padding: 16px;
		text-align: center;
		color: var(--text-secondary);
		font-size: 14px;
	}

	.dataset-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.dataset-card {
		padding: 12px;
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 8px;
		display: flex;
		gap: 12px;
		align-items: flex-start;
		transition: all 0.2s;
	}

	.dataset-card:hover {
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
		border-color: rgba(0, 0, 0, 0.2);
	}

	.dataset-info {
		flex: 1;
		min-width: 0;
	}

	h5 {
		margin: 0 0 4px 0;
		font-size: 14px;
		font-weight: 600;
	}

	.description {
		margin: 0 0 8px 0;
		font-size: 12px;
		color: var(--text-secondary);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.dataset-meta {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.download-btn {
		width: 32px;
		height: 32px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.2);
		background: white;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		flex-shrink: 0;
	}

	.download-btn:hover:not(:disabled) {
		background: rgba(0, 0, 0, 0.05);
		border-color: rgba(0, 0, 0, 0.3);
	}

	.download-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.download-btn.downloading {
		animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
	}

	.spinner {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	/* Tooltip styles */
	.info-tooltip {
		position: relative;
		display: inline-block;
	}

	.info-btn {
		width: 20px;
		height: 20px;
		border-radius: 50%;
		border: 1px solid rgba(0,0,0,0.15);
		background: white;
		font-size: 12px;
		line-height: 18px;
		padding: 0;
		cursor: pointer;
	}

	.tooltip-content {
		position: absolute;
		left: 24px;
		top: -6px;
		min-width: 220px;
		background: white;
		border: 1px solid rgba(0,0,0,0.12);
		padding: 8px;
		border-radius: 6px;
		box-shadow: 0 4px 12px rgba(0,0,0,0.08);
		display: none;
		z-index: 40;
		font-size: 12px;
	}

	.info-tooltip:hover .tooltip-content {
		display: block;
	}
</style>
