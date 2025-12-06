<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { slide } from 'svelte/transition';
	import ServersTab from './ServersTab.svelte';
	import AnalyticsTab from './AnalyticsTab.svelte';

	export let open = false;

	const dispatch = createEventDispatcher();

	type Tab = 'catalogue' | 'analytics';
	let activeTab: Tab = 'catalogue';

	// Sidebar width management
	let sidebarWidth = 400;
	let isResizing = false;

	onMount(() => {
		// Load saved width from localStorage
		const saved = localStorage.getItem('sidebar-width');
		if (saved) {
			sidebarWidth = parseInt(saved, 10);
		}
	});

	function close() {
		dispatch('close');
	}

	function startResize() {
		isResizing = true;
	}

	function stopResize() {
		if (isResizing) {
			isResizing = false;
			// Save width to localStorage
			localStorage.setItem('sidebar-width', sidebarWidth.toString());
		}
	}

	function resize(event: MouseEvent) {
		if (isResizing) {
			// Calculate new width based on mouse position
			const newWidth = event.clientX;
			// Constrain width between 300px and 800px
			sidebarWidth = Math.max(300, Math.min(800, newWidth));
		}
	}
</script>

<svelte:window on:mousemove={resize} on:mouseup={stopResize} />

{#if open}
	<div class="sidebar-overlay" on:click={close} transition:slide={{ duration: 200 }}></div>
	<div class="sidebar" style="width: {sidebarWidth}px" transition:slide={{ duration: 300, axis: 'x' }}>
		<div class="sidebar-header">
			<img src="/logo.png" alt="Spheraform" class="logo" />
			<button class="close-btn" on:click={close} aria-label="Close sidebar">
				<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<line x1="18" y1="6" x2="6" y2="18"></line>
					<line x1="6" y1="6" x2="18" y2="18"></line>
				</svg>
			</button>
		</div>

		<div class="tabs">
			<button
				class="tab"
				class:active={activeTab === 'catalogue'}
				on:click={() => activeTab = 'catalogue'}
			>
				Catalogue
			</button>
			<button
				class="tab"
				class:active={activeTab === 'analytics'}
				on:click={() => activeTab = 'analytics'}
			>
				Analytics
			</button>
		</div>

		<div class="tab-content">
			{#if activeTab === 'catalogue'}
				<ServersTab {sidebarWidth} />
			{:else if activeTab === 'analytics'}
				<AnalyticsTab />
			{/if}
		</div>

		<div
			class="resize-handle"
			class:resizing={isResizing}
			on:mousedown={startResize}
			role="separator"
			aria-label="Resize sidebar"
		></div>
	</div>
{/if}

<style>
	.sidebar-overlay {
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		background: rgba(0, 0, 0, 0.3);
		z-index: 1999;
	}

	.sidebar {
		position: fixed;
		top: 0;
		left: 0;
		height: 100%;
		background: rgba(255, 255, 255, 0.95);
		backdrop-filter: blur(20px);
		-webkit-backdrop-filter: blur(20px);
		box-shadow: 2px 0 12px rgba(0, 0, 0, 0.1);
		z-index: 2000;
		display: flex;
		flex-direction: column;
	}

	.resize-handle {
		position: absolute;
		top: 0;
		right: 0;
		width: 8px;
		height: 100%;
		cursor: ew-resize;
		background: transparent;
		transition: background 0.2s;
		z-index: 10;
	}

	.resize-handle:hover,
	.resize-handle.resizing {
		background: rgba(0, 0, 0, 0.1);
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 24px;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.logo {
		height: 70px;
		width: 100%;
		object-fit: contain;
	}

	.close-btn {
		width: 36px;
		height: 36px;
		border: none;
		background: none;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		transition: background 0.2s;
	}

	.close-btn:hover {
		background: rgba(0, 0, 0, 0.05);
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
		padding: 0 24px;
	}

	.tab {
		flex: 1;
		padding: 16px 8px;
		border: none;
		background: none;
		cursor: pointer;
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		border-bottom: 2px solid transparent;
		transition: all 0.2s;
	}

	.tab:hover {
		color: var(--text-primary);
	}

	.tab.active {
		color: var(--text-primary);
		border-bottom-color: var(--text-primary);
	}

	.tab-content {
		flex: 1;
		overflow-y: auto;
		padding: 24px;
		position: relative;
	}
</style>
