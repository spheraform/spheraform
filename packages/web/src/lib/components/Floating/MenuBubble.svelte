<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();
</script>

<button class="menu-bubble" on:click={() => dispatch('click')} aria-label="Toggle menu">
	<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
		<line x1="3" y1="12" x2="21" y2="12"></line>
		<line x1="3" y1="6" x2="21" y2="6"></line>
		<line x1="3" y1="18" x2="21" y2="18"></line>
	</svg>
</button>

<style>
	.menu-bubble {
		position: fixed;
		top: 20px;
		left: 20px;
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
		z-index: 1000;
	}

	.menu-bubble:hover {
		background: rgba(255, 255, 255, 0.2);
		transform: scale(1.05);
	}

	.menu-bubble:active {
		transform: scale(0.95);
	}

	svg {
		color: var(--text-primary);
	}
</style>
