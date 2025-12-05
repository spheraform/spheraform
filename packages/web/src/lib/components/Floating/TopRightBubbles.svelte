<script lang="ts">
	let docsOpen = false;
	let userOpen = false;

	function toggleDocs() {
		docsOpen = !docsOpen;
		userOpen = false;
	}

	function toggleUser() {
		userOpen = !userOpen;
		docsOpen = false;
	}
</script>

<div class="top-right">
	<div class="bubble-container">
		<button class="bubble" on:click={toggleDocs} aria-label="Documentation">
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
				<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
			</svg>
		</button>
		{#if docsOpen}
			<div class="dropdown">
				<a href="https://github.com/spheraform/spheraform" target="_blank">GitHub</a>
				<a href="#" on:click|preventDefault={() => alert('API Docs')}>API Docs</a>
				<a href="#" on:click|preventDefault={() => alert('About')}>About</a>
			</div>
		{/if}
	</div>

	<div class="bubble-container">
		<button class="bubble" on:click={toggleUser} aria-label="User menu">
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
				<circle cx="12" cy="7" r="4"></circle>
			</svg>
		</button>
		{#if userOpen}
			<div class="dropdown">
				<a href="#" on:click|preventDefault={() => alert('Profile')}>Profile</a>
				<a href="#" on:click|preventDefault={() => alert('Settings')}>Settings</a>
				<a href="#" on:click|preventDefault={() => alert('Logout')}>Logout</a>
			</div>
		{/if}
	</div>
</div>

<style>
	.top-right {
		position: fixed;
		top: 20px;
		right: 20px;
		display: flex;
		gap: 12px;
		z-index: 1000;
	}

	.bubble-container {
		position: relative;
	}

	.bubble {
		width: 48px;
		height: 48px;
		border: none;
		border-radius: 50%;
		background: var(--glass-bg);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid var(--glass-border);
		box-shadow: 0 4px 6px var(--glass-shadow);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
	}

	.bubble:hover {
		background: rgba(255, 255, 255, 0.2);
		transform: scale(1.05);
	}

	.bubble:active {
		transform: scale(0.95);
	}

	svg {
		color: var(--text-primary);
	}

	.dropdown {
		position: absolute;
		top: 56px;
		right: 0;
		min-width: 160px;
		background: var(--glass-bg);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid var(--glass-border);
		border-radius: 12px;
		box-shadow: 0 4px 12px var(--glass-shadow);
		padding: 8px 0;
		display: flex;
		flex-direction: column;
	}

	.dropdown a {
		padding: 10px 16px;
		color: var(--text-primary);
		text-decoration: none;
		font-size: 14px;
		transition: background 0.2s;
	}

	.dropdown a:hover {
		background: rgba(255, 255, 255, 0.1);
	}
</style>
