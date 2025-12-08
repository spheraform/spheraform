<script lang="ts">
	import { onMount } from 'svelte';
	import { mapStore } from '$lib/stores/mapStore';

	interface Dataset {
		id: string;
		name: string;
		description: string | null;
		feature_count: number | null;
		is_active: boolean;
		is_cached: boolean;
		cache_table: string | null;
		access_url?: string;
		updated_at?: string | null;
		themes?: string[] | null;
		bbox?: string | null;
		source_srid?: number | null;
		geometry_type?: string | null;
		last_fetched_at?: string | null;
	}

	let datasets: Dataset[] = [];
	let loading = true;
	let error: string | null = null;

	onMount(async () => {
		try {
			const response = await fetch('/api/v1/datasets?limit=50');
			if (!response.ok) throw new Error('Failed to fetch datasets');
			datasets = await response.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			loading = false;
		}
	});

	async function downloadDataset(datasetId: string) {
		try {
			const response = await fetch(`/api/v1/download/${datasetId}/file`);
			if (!response.ok) throw new Error('Failed to download dataset');

			const blob = await response.blob();
			const url = window.URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `dataset_${datasetId}.geojson`;
			document.body.appendChild(a);
			a.click();
			window.URL.revokeObjectURL(url);
			document.body.removeChild(a);
		} catch (e) {
			alert('Error downloading dataset: ' + (e instanceof Error ? e.message : 'Unknown error'));
		}
	}

	async function viewOnMap(dataset: Dataset) {
		if (!dataset.cache_table) {
			// Dataset not cached yet, trigger download first
			try {
				const response = await fetch('/api/v1/download', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({
						dataset_ids: [dataset.id],
						format: 'geojson',
						merge: false
					})
				});

				if (!response.ok) throw new Error('Failed to cache dataset');

				const result = await response.json();

				// Refresh datasets to get cache_table
				const refreshResponse = await fetch('/api/v1/datasets?limit=50');
				datasets = await refreshResponse.json();

				const updatedDataset = datasets.find(d => d.id === dataset.id);
				if (updatedDataset?.cache_table) {
					mapStore.addLayer(updatedDataset.id, updatedDataset.name, updatedDataset.cache_table);
				}
			} catch (e) {
				alert('Error caching dataset: ' + (e instanceof Error ? e.message : 'Unknown error'));
			}
		} else {
			mapStore.addLayer(dataset.id, dataset.name, dataset.cache_table);
		}
	}
</script>

<div class="datasets-tab">
	<div class="header">
		<h3>Datasets</h3>
		<p class="subtitle">{datasets.length} datasets found</p>
	</div>

	{#if loading}
		<div class="loading">Loading datasets...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if datasets.length === 0}
		<div class="empty">No datasets available. Crawl some servers first!</div>
	{:else}
		<div class="dataset-list">
			{#each datasets as dataset}
				<div class="dataset-card" class:cached={dataset.is_cached}>
					<div class="dataset-info">
						<div class="title-row">
							<h4>{dataset.name}</h4>
							{#if dataset.is_cached}
								<span class="cached-check" title="Cached and ready">✓</span>
							{/if}
						</div>
						{#if dataset.description}
							<p class="description">{dataset.description}</p>
						{/if}
						<div class="meta">
							{#if dataset.feature_count}
								<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
							{/if}
							{#if dataset.themes && dataset.themes.length > 0}
								{#each dataset.themes.slice(0, 2) as theme}
									<span class="badge theme">{theme.replace(/_/g, ' ')}</span>
								{/each}
							{/if}
							{#if dataset.geometry_type}
								<span class="badge geom-type">{dataset.geometry_type}</span>
							{/if}
							<div class="info-tooltip">
								<button class="info-btn" aria-label="More info">i</button>
								<div class="tooltip-content">
									<div><strong>URL:</strong> <a href="{dataset.access_url}" target="_blank" rel="noopener noreferrer">{dataset.access_url}</a></div>
									<div><strong>Updated:</strong> {dataset.updated_at ? new Date(dataset.updated_at).toLocaleString() : 'N/A'}</div>
									{#if dataset.last_fetched_at}
										<div><strong>Last Fetched:</strong> {new Date(dataset.last_fetched_at).toLocaleString()}</div>
									{/if}
									<div><strong>Features:</strong> {dataset.feature_count ?? 'N/A'}</div>
									{#if dataset.source_srid}
										<div><strong>Source SRID:</strong> {dataset.source_srid}</div>
									{/if}
									{#if dataset.bbox}
										<div><strong>Bbox:</strong> <span class="bbox-text">{dataset.bbox.substring(0, 50)}...</span></div>
									{/if}
								</div>
							</div>
							{#if !dataset.is_active}
								<span class="badge inactive">Inactive</span>
							{/if}
						</div>
					</div>
					<div class="actions">
						<button
							class="map-btn"
							on:click={() => viewOnMap(dataset)}
							title={dataset.is_cached ? "View on map" : "Cache and view on map"}
						>
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4z"></path>
								<line x1="8" y1="2" x2="8" y2="18"></line>
								<line x1="16" y1="6" x2="16" y2="22"></line>
							</svg>
						</button>
						<button class="download-btn" on:click={() => downloadDataset(dataset.id)}>
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
								<polyline points="7 10 12 15 17 10"></polyline>
								<line x1="12" y1="15" x2="12" y2="3"></line>
							</svg>
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.datasets-tab {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.header {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
	}

	.subtitle {
		margin: 0;
		font-size: 14px;
		color: var(--text-secondary);
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

	.dataset-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.dataset-card {
		padding: 16px;
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		display: flex;
		gap: 12px;
		align-items: flex-start;
		transition: all 0.2s;
	}

	.dataset-card.cached {
		background: rgba(34, 197, 94, 0.05);
		border-color: rgba(34, 197, 94, 0.2);
	}

	.dataset-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.dataset-info {
		flex: 1;
		min-width: 0;
	}

	.title-row {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 4px;
	}

	h4 {
		margin: 0;
		font-size: 16px;
		font-weight: 600;
	}

	.cached-check {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 20px;
		height: 20px;
		background: #22c55e;
		color: white;
		border-radius: 50%;
		font-size: 12px;
		font-weight: bold;
	}

	.description {
		margin: 0 0 8px 0;
		font-size: 13px;
		color: var(--text-secondary);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	/* Tooltip styles (same as ServersTab) */
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
		font-weight: 500;
		text-transform: capitalize;
	}

	.badge.inactive {
		background: #fee;
		color: #dc2626;
	}

	.badge.theme {
		background: rgba(59, 130, 246, 0.1);
		color: #2563eb;
	}

	.badge.geom-type {
		background: rgba(168, 85, 247, 0.1);
		color: #7c3aed;
	}

	.bbox-text {
		font-family: monospace;
		font-size: 11px;
		word-break: break-all;
	}

	.actions {
		display: flex;
		gap: 8px;
	}

	.map-btn,
	.download-btn {
		width: 36px;
		height: 36px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.2);
		background: white;
		border-radius: 8px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
	}

	.map-btn:hover,
	.download-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}

	.map-btn {
		color: #3b82f6;
		border-color: #3b82f6;
	}

	.map-btn:hover {
		background: rgba(59, 130, 246, 0.1);
	}
</style>
