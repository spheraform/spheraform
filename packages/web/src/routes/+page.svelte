<script lang="ts">
	import { onMount } from 'svelte';
	import Map from '$lib/components/Map/Map.svelte';
	import MenuBubble from '$lib/components/Floating/MenuBubble.svelte';
	import SearchBar from '$lib/components/Floating/SearchBar.svelte';
	import TopRightBubbles from '$lib/components/Floating/TopRightBubbles.svelte';
	import Sidebar from '$lib/components/Sidebar/Sidebar.svelte';

	let sidebarOpen = false;

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
	}
</script>

<div class="app">
	<Map />

	<MenuBubble on:click={toggleSidebar} />
	<SearchBar />
	<TopRightBubbles />

	<Sidebar open={sidebarOpen} on:close={() => sidebarOpen = false} />
</div>

<style>
	.app {
		position: relative;
		width: 100vw;
		height: 100vh;
		overflow: hidden;
	}
</style>
