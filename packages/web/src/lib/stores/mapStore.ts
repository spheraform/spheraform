import { writable } from 'svelte/store';
import type { Map } from 'maplibre-gl';

export interface MapStore {
	map: Map | null;
}

function createMapStore() {
	const { subscribe, set, update } = writable<MapStore>({
		map: null
	});

	return {
		subscribe,
		setMap: (map: Map) => update(state => ({ ...state, map })),
		addLayer: (datasetId: string, cacheTable: string) => {
			update(state => {
				if (!state.map) return state;

				const map = state.map;
				const sourceId = `dataset-${datasetId}`;
				const layerId = `layer-${datasetId}`;

				// Remove existing source and layer if they exist
				if (map.getLayer(layerId)) {
					map.removeLayer(layerId);
				}
				if (map.getSource(sourceId)) {
					map.removeSource(sourceId);
				}

				// Add vector tile source from Martin
				map.addSource(sourceId, {
					type: 'vector',
					tiles: [`http://localhost:3000/${cacheTable}/{z}/{x}/{y}.pbf`],
					minzoom: 0,
					maxzoom: 14
				});

				// Add layer based on geometry type
				// For now, we'll create a generic style that works for all types
				map.addLayer({
					id: layerId,
					type: 'line',
					source: sourceId,
					'source-layer': cacheTable,
					paint: {
						'line-color': '#3b82f6',
						'line-width': 2
					}
				});

				// Also add a fill layer for polygons
				map.addLayer({
					id: `${layerId}-fill`,
					type: 'fill',
					source: sourceId,
					'source-layer': cacheTable,
					paint: {
						'fill-color': '#3b82f6',
						'fill-opacity': 0.3
					}
				});

				return state;
			});
		},
		removeLayer: (datasetId: string) => {
			update(state => {
				if (!state.map) return state;

				const map = state.map;
				const sourceId = `dataset-${datasetId}`;
				const layerId = `layer-${datasetId}`;

				if (map.getLayer(layerId)) {
					map.removeLayer(layerId);
				}
				if (map.getLayer(`${layerId}-fill`)) {
					map.removeLayer(`${layerId}-fill`);
				}
				if (map.getSource(sourceId)) {
					map.removeSource(sourceId);
				}

				return state;
			});
		}
	};
}

export const mapStore = createMapStore();
