<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { mapStore } from '$lib/stores/mapStore';

	let mapContainer: HTMLDivElement;
	let map: maplibregl.Map;

	onMount(() => {
		map = new maplibregl.Map({
			container: mapContainer,
			style: {
				version: 8,
				sources: {
					'osm': {
						type: 'raster',
						tiles: ['https://tiles.stadiamaps.com/tiles/stamen_toner-dark/{z}/{x}/{y}.png'],
						tileSize: 256,
						attribution: '&copy; Stadia Maps, &copy: Stamen Design, &copy; OpenMapTils &copy; OpenStreetMap contributors'
					}
				},
				layers: [
					{
						id: 'osm',
						type: 'raster',
						source: 'osm',
						minzoom: 0,
						maxzoom: 19
					}
				]
			},
			center: [-2.5, 54], // UK center
			zoom: 5
		});

		map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
		map.addControl(new maplibregl.ScaleControl(), 'bottom-left');

		// Register map in store when ready
		map.on('load', () => {
			mapStore.setMap(map);
		});
	});

	onDestroy(() => {
		map?.remove();
	});
</script>

<div bind:this={mapContainer} class="map-container"></div>

<style>
	.map-container {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
	}
</style>
