<script lang="ts">
	import { onMount } from 'svelte';
	import Map from '$lib/components/Map/Map.svelte';
	import MenuBubble from '$lib/components/Floating/MenuBubble.svelte';
	import SearchBar from '$lib/components/Floating/SearchBar.svelte';
	import TopRightBubbles from '$lib/components/Floating/TopRightBubbles.svelte';
	import Sidebar from '$lib/components/Sidebar/Sidebar.svelte';

	export let data;

	let sidebarOpen = false;

	onMount(() => {
		// Load saved sidebar state from localStorage
		const saved = localStorage.getItem('sidebar-open');
		if (saved !== null) {
			sidebarOpen = saved === 'true';
		}
	});

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
		// Save state to localStorage
		localStorage.setItem('sidebar-open', sidebarOpen.toString());
	}

	function closeSidebar() {
		sidebarOpen = false;
		// Save state to localStorage
		localStorage.setItem('sidebar-open', 'false');
	}
</script>

<div class="app">
	<Map />

	<MenuBubble on:click={toggleSidebar} />
	<SearchBar />
	<TopRightBubbles />

	<Sidebar open={sidebarOpen} on:close={closeSidebar} />
</div>

<style>
	.app {
		position: relative;
		width: 100vw;
		height: 100vh;
		overflow: hidden;
	}
</style>
