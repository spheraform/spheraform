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
		addLayer: (datasetId: string, datasetName: string, cacheTable: string, geometryType?: string) => {
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

				// Normalize geometry type (handle variations like "Point", "esriGeometryPoint", etc.)
				const normalizedType = geometryType?.toLowerCase() || '';
				const isPoint = normalizedType.includes('point');
				const isLine = normalizedType.includes('line') || normalizedType.includes('string');
				const isPolygon = normalizedType.includes('polygon');

				// For Point geometries, add circle layer
				if (isPoint || !geometryType) {
					map.addLayer({
						id: layerId,
						type: 'circle',
						source: sourceId,
						'source-layer': cacheTable,
						minzoom: 0,
						maxzoom: 22,
						paint: {
							'circle-radius': [
								'interpolate',
								['linear'],
								['zoom'],
								0, 2,    // radius 2px at zoom 0
								10, 4,   // radius 4px at zoom 10
								15, 6,   // radius 6px at zoom 15
								22, 10   // radius 10px at zoom 22
							],
							'circle-color': color,
							'circle-opacity': 0.8,
							'circle-stroke-color': '#ffffff',
							'circle-stroke-width': 1
						}
					});
				}

				// For LineString geometries, add line layer
				if (isLine || !geometryType) {
					map.addLayer({
						id: isLine ? layerId : `${layerId}-line`,
						type: 'line',
						source: sourceId,
						'source-layer': cacheTable,
						minzoom: 0,
						maxzoom: 22,
						paint: {
							'line-color': color,
							'line-width': 2
						}
					});
				}

				// For Polygon geometries, add fill + outline layers
				if (isPolygon || !geometryType) {
					map.addLayer({
						id: `${layerId}-fill`,
						type: 'fill',
						source: sourceId,
						'source-layer': cacheTable,
						minzoom: 0,
						maxzoom: 22,
						paint: {
							'fill-color': color,
							'fill-opacity': 0.3
						}
					});

					map.addLayer({
						id: `${layerId}-outline`,
						type: 'line',
						source: sourceId,
						'source-layer': cacheTable,
						minzoom: 0,
						maxzoom: 22,
						paint: {
							'line-color': color,
							'line-width': 2
						}
					});
				}

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

				// Remove all possible layer types
				const layerIds = [
					layerId,              // Main layer (circle or line)
					`${layerId}-fill`,    // Polygon fill
					`${layerId}-outline`, // Polygon outline
					`${layerId}-line`,    // Line geometry
				];

				layerIds.forEach(id => {
					if (map.getLayer(id)) {
						map.removeLayer(id);
					}
				});

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
