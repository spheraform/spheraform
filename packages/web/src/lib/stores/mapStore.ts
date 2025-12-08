import { writable } from 'svelte/store';
import type { Map } from 'maplibre-gl';

export interface ActiveDataset {
	id: string;
	name: string;
	color: string;
	cacheTable: string;
}

export interface MapStore {
	map: Map | null;
	activeDatasets: ActiveDataset[];
}

// Generate a truly random color
function generateRandomColor(): string {
	const color = Math.floor(Math.random() * 16777215).toString(16);
	// Pad with zeros if needed to ensure 6 characters
	return '#' + color.padStart(6, '0');
}

function createMapStore() {
	const { subscribe, set, update } = writable<MapStore>({
		map: null,
		activeDatasets: []
	});

	return {
		subscribe,
		setMap: (map: Map) => update(state => ({ ...state, map })),
		addLayer: (datasetId: string, datasetName: string, cacheTable: string) => {
			update(state => {
				if (!state.map) return state;

				const map = state.map;
				const sourceId = `dataset-${datasetId}`;
				const layerId = `layer-${datasetId}`;

				// Generate a random color for this dataset
				const color = generateRandomColor();

				// Remove existing source and layer if they exist
				if (map.getLayer(layerId)) {
					map.removeLayer(layerId);
				}
				if (map.getLayer(`${layerId}-fill`)) {
					map.removeLayer(`${layerId}-fill`);
				}
				if (map.getSource(sourceId)) {
					map.removeSource(sourceId);
				}

				// Add vector tile source from Martin
				map.addSource(sourceId, {
					type: 'vector',
					tiles: [`http://localhost:3000/${cacheTable}/{z}/{x}/{y}`],
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
						'line-color': color,
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
						'fill-color': color,
						'fill-opacity': 0.3
					}
				});

				// Add to active datasets if not already there
				const existingIndex = state.activeDatasets.findIndex(d => d.id === datasetId);
				if (existingIndex >= 0) {
					// Update existing entry with new color
					state.activeDatasets[existingIndex] = { id: datasetId, name: datasetName, color, cacheTable };
				} else {
					// Add new entry
					state.activeDatasets = [...state.activeDatasets, { id: datasetId, name: datasetName, color, cacheTable }];
				}

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

				// Remove from active datasets
				state.activeDatasets = state.activeDatasets.filter(d => d.id !== datasetId);

				return state;
			});
		}
	};
}

export const mapStore = createMapStore();
