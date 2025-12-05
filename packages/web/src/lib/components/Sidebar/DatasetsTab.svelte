<script lang="ts">
	import { onMount } from 'svelte';

	interface Dataset {
		id: string;
		name: string;
		description: string | null;
		feature_count: number | null;
		is_active: boolean;
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
				<div class="dataset-card">
					<div class="dataset-info">
						<h4>{dataset.name}</h4>
						{#if dataset.description}
							<p class="description">{dataset.description}</p>
						{/if}
						<div class="meta">
							{#if dataset.feature_count}
								<span class="badge">{dataset.feature_count.toLocaleString()} features</span>
							{/if}
							{#if !dataset.is_active}
								<span class="badge inactive">Inactive</span>
							{/if}
						</div>
					</div>
					<button class="download-btn" on:click={() => downloadDataset(dataset.id)}>
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
							<polyline points="7 10 12 15 17 10"></polyline>
							<line x1="12" y1="15" x2="12" y2="3"></line>
						</svg>
					</button>
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
		transition: box-shadow 0.2s;
	}

	.dataset-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.dataset-info {
		flex: 1;
		min-width: 0;
	}

	h4 {
		margin: 0 0 4px 0;
		font-size: 16px;
		font-weight: 600;
	}

	.description {
		margin: 0 0 8px 0;
		font-size: 13px;
		color: var(--text-secondary);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
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
	}

	.badge.inactive {
		background: #fee;
		color: #dc2626;
	}

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

	.download-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}
</style>
