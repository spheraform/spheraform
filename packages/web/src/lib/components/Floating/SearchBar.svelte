<script lang="ts">
	let searchQuery = '';

	function handleSearch() {
		console.log('Search:', searchQuery);
		// TODO: Implement search functionality
	}
</script>

<div class="search-container">
	<div class="search-bar">
		<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
			<circle cx="11" cy="11" r="8"></circle>
			<path d="m21 21-4.35-4.35"></path>
		</svg>
		<input
			type="text"
			placeholder="Search datasets..."
			bind:value={searchQuery}
			on:keydown={(e) => e.key === 'Enter' && handleSearch()}
		/>
	</div>
</div>

<style>
	.search-container {
		position: fixed;
		top: 20px;
		left: 90px;
		z-index: 1000;
	}

	.search-bar {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 20px;
		min-width: 300px;
		background: rgba(255, 255, 255, 0.95);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid var(--glass-border);
		border-radius: 24px;
		box-shadow: 0 4px 6px var(--glass-shadow);
		transition: all 0.2s;
	}

	.search-bar:focus-within {
		background: rgba(255, 255, 255, 0.15);
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
	}

	svg {
		color: var(--text-secondary);
		flex-shrink: 0;
	}

	input {
		flex: 1;
		border: none;
		background: none;
		outline: none;
		font-size: 14px;
		color: var(--text-primary);
	}

	input::placeholder {
		color: var(--text-secondary);
	}
</style>
