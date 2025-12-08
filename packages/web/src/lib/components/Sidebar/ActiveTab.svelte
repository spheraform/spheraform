<script lang="ts">
	import { mapStore } from '$lib/stores/mapStore';

	function removeDataset(datasetId: string) {
		mapStore.removeLayer(datasetId);
	}
</script>

<div class="active-tab">
	<div class="header">
		<h3>Active Datasets</h3>
		<p class="subtitle">{$mapStore.activeDatasets.length} dataset{$mapStore.activeDatasets.length !== 1 ? 's' : ''} loaded</p>
	</div>

	{#if $mapStore.activeDatasets.length === 0}
		<div class="empty">No datasets loaded on map. Add datasets from the Catalogue tab.</div>
	{:else}
		<div class="dataset-list">
			{#each $mapStore.activeDatasets as dataset}
				<div class="dataset-card">
					<div class="color-indicator" style="background-color: {dataset.color}"></div>
					<div class="dataset-info">
						<h4>{dataset.name}</h4>
						<p class="cache-table">{dataset.cacheTable}</p>
					</div>
					<button class="remove-btn" on:click={() => removeDataset(dataset.id)} title="Remove from map">
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<line x1="18" y1="6" x2="6" y2="18"></line>
							<line x1="6" y1="6" x2="18" y2="18"></line>
						</svg>
					</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.active-tab {
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

	.empty {
		padding: 24px;
		text-align: center;
		color: var(--text-secondary);
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
		align-items: center;
		transition: all 0.2s;
	}

	.dataset-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.color-indicator {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		border: 2px solid rgba(0, 0, 0, 0.1);
		flex-shrink: 0;
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

	.cache-table {
		margin: 0;
		font-size: 12px;
		color: var(--text-secondary);
		font-family: monospace;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.remove-btn {
		width: 32px;
		height: 32px;
		padding: 0;
		border: 1px solid rgba(220, 38, 38, 0.3);
		background: white;
		border-radius: 8px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		color: #dc2626;
		flex-shrink: 0;
	}

	.remove-btn:hover {
		background: rgba(220, 38, 38, 0.1);
		border-color: #dc2626;
	}
</style>
