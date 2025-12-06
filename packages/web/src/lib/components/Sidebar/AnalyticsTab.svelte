<script lang="ts">
	// Placeholder for analytics/stats
	let stats = {
		servers: 0,
		datasets: 0,
		totalFeatures: 0
	};
</script>

<div class="analytics-tab">
	<h3>Analytics</h3>
	<p class="subtitle">System statistics and insights</p>

	<div class="stats-grid">
		<div class="stat-card">
			<div class="stat-value">{stats.servers}</div>
			<div class="stat-label">Servers</div>
		</div>
		<div class="stat-card">
			<div class="stat-value">{stats.datasets}</div>
			<div class="stat-label">Datasets</div>
		</div>
		<div class="stat-card">
			<div class="stat-value">{stats.totalFeatures.toLocaleString()}</div>
			<div class="stat-label">Total Features</div>
		</div>
	</div>

	<div class="placeholder">
		<p>Analytics features coming soon:</p>
		<ul>
			<li>Coverage maps</li>
			<li>Download statistics</li>
			<li>Data quality metrics</li>
			<li>Usage analytics</li>
		</ul>
	</div>
</div>

<style>
	.analytics-tab {
		display: flex;
		flex-direction: column;
		gap: 16px;
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

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 12px;
	}

	.stat-card {
		padding: 16px;
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		text-align: center;
	}

	.stat-value {
		font-size: 24px;
		font-weight: 700;
		color: var(--text-primary);
	}

	.stat-label {
		margin-top: 4px;
		font-size: 12px;
		color: var(--text-secondary);
	}

	.placeholder {
		padding: 24px;
		background: rgba(0, 0, 0, 0.02);
		border-radius: 12px;
		text-align: center;
	}

	.placeholder p {
		margin: 0 0 12px 0;
		color: var(--text-secondary);
	}

	.placeholder ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.placeholder li {
		color: var(--text-secondary);
		font-size: 14px;
	}
</style>
