<script lang="ts">
	import { onMount } from 'svelte';
	import { mapStore } from '$lib/stores/mapStore';
	import ServerForm from '$lib/components/Modals/ServerForm.svelte';
	import ConfirmModal from '$lib/components/Modals/ConfirmModal.svelte';
	import InfoModal from '$lib/components/Modals/InfoModal.svelte';
	import InfoDetailModal from '$lib/components/Modals/InfoDetailModal.svelte';
	import { pollJobStatus, formatJobProgress } from '$lib/utils/polling';

	interface Server {
		id: string;
		name: string;
		base_url: string;
		provider_type: string;
		country: string;
		is_active: boolean;
		health_status: string | null;
		last_crawl: string | null;
		// UI state
		expanded?: boolean;
		loading?: boolean;
		crawling?: boolean;
		datasets?: any[];
		crawlJobId?: string;
		crawlJobStatus?: any;
	}

	export let sidebarWidth: number = 400;
	export let martinUrl: string;

	let servers: Server[] = [];
	let loading = true;
	let error: string | null = null;

	// Filtering and sorting state
	let filterCountry = '';
	let filterServerType = '';
	let filterHealthStatus = '';
	let sortBy: 'name' | 'country' | '' = '';
	let sortAscending = true;

	// Global dataset search state
	let globalDatasetSearch = '';

	// Track which datasets are currently being fetched
	let fetchingDatasets: {[datasetId: string]: boolean} = {};

	// Function to filter datasets based on global search
	function filterDatasetsBySearch(datasets: any[]) {
		if (!globalDatasetSearch) return datasets;

		const searchQuery = globalDatasetSearch.toLowerCase();
		return datasets.filter(d =>
			d.name?.toLowerCase().includes(searchQuery) ||
			d.description?.toLowerCase().includes(searchQuery) ||
			d.themes?.some((t: string) => t.toLowerCase().includes(searchQuery)) ||
			d.keywords?.some((k: string) => k.toLowerCase().includes(searchQuery))
		);
	}

	// Function to sort datasets by cached status (always cached first)
	function sortDatasetsByCached(datasets: any[]) {
		return [...datasets].sort((a, b) => {
			// Cached first
			if (a.is_cached && !b.is_cached) return -1;
			if (!a.is_cached && b.is_cached) return 1;
			return 0;
		});
	}

	// Auto-load datasets for all servers when search is active
	$: if (globalDatasetSearch) {
		servers.forEach(server => {
			if (!server.datasets && !server.loading) {
				loadDatasets(server);
			}
		});
	}

	// Grid view: activate when sidebar is wider than 600px
	$: useGridView = sidebarWidth > 600;

	// Get unique values for filter dropdowns
	$: countries = [...new Set(servers.map(s => s.country).filter(Boolean))].sort();
	$: serverTypes = [...new Set(servers.map(s => s.provider_type).filter(Boolean))].sort();
	$: healthStatuses = [...new Set(servers.map(s => s.health_status).filter(Boolean))].sort();

	// Filtered and sorted servers
	$: filteredServers = servers
		.filter(s => !filterCountry || s.country === filterCountry)
		.filter(s => !filterServerType || s.provider_type === filterServerType)
		.filter(s => !filterHealthStatus || s.health_status === filterHealthStatus)
		.filter(s => {
			// If there's a global search, only show servers with matching datasets
			if (globalDatasetSearch && s.datasets && s.datasets.length > 0) {
				const matchingDatasets = filterDatasetsBySearch(s.datasets);
				return matchingDatasets.length > 0;
			}
			return true;
		})
		.sort((a, b) => {
			if (!sortBy) return 0;
			const aVal = a[sortBy] || '';
			const bVal = b[sortBy] || '';
			const comparison = aVal.localeCompare(bVal);
			return sortAscending ? comparison : -comparison;
		});

	// Modal state
	let showAddModal = false;
	let showEditModal = false;
	let editInitial: any = null;
	let serverBeingEdited: Server | null = null;

	let showConfirmDelete = false;
	let serverToDelete: Server | null = null;

	let showInfoModal = false;
	let infoMessage = '';

	// Detail modal state
	let showDetailModal = false;
	let detailModalTitle = '';
	let detailModalRows: Array<{ label: string; value: string; link?: boolean }> = [];

	async function loadServers() {
		try {
			const response = await fetch('/api/v1/servers');
			if (!response.ok) throw new Error('Failed to fetch servers');
			const list = await response.json();

			// Preserve existing UI state (expanded, loading, crawling) when reloading
			const stateMap = new Map(servers.map(s => [s.id, {
				expanded: s.expanded,
				loading: s.loading,
				crawling: s.crawling,
				crawlJobId: s.crawlJobId,
				crawlJobStatus: s.crawlJobStatus,
				datasets: s.datasets
			}]));

			servers = list.map((s: any) => {
				const existingState = stateMap.get(s.id);
				return {
					...s,
					expanded: existingState?.expanded || false,
					loading: existingState?.loading || false,
					crawling: existingState?.crawling || false,
					crawlJobId: existingState?.crawlJobId,
					crawlJobStatus: existingState?.crawlJobStatus,
					datasets: existingState?.datasets
				};
			});
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
			throw e;
		}
	}

	onMount(async () => {
		try {
			await loadServers();

			// Resume any in-progress crawl jobs
			await resumeCrawlJobs();

			// Resume any in-progress download jobs
			await resumeDownloadJobs();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			loading = false;
		}
	});

	async function resumeCrawlJobs() {
		// Check each server for running/pending crawl jobs
		for (const server of servers) {
			const serverId = server.id; // Capture server ID to avoid closure issues
			try {
				const res = await fetch(`/api/v1/servers/${serverId}/crawl/latest`);
				if (res.ok) {
					const job = await res.json();
					if (job && (job.status === 'running' || job.status === 'pending')) {
						// Resume polling this job
						servers = servers.map(s =>
							s.id === serverId ? { ...s, crawling: true, crawlJobId: job.id, crawlJobStatus: job } : s
						);

						// Start polling
						pollJobStatus(
							`/api/v1/servers/crawl/${job.id}`,
							(progressJob) => {
								servers = servers.map(s =>
									s.id === serverId ? { ...s, crawlJobStatus: progressJob } : s
								);
							},
							{ interval: 2500, timeout: 600000 }
						).then((finalJob) => {
							// Job completed
							if (finalJob.status === 'completed') {
								const srv = servers.find(s => s.id === serverId);
								if (srv?.expanded) {
									refreshServerDatasets(serverId);
								}
							} else if (finalJob.status === 'failed') {
								console.warn(`Crawl job ${job.id} failed:`, finalJob.error);
							}
						}).catch((error) => {
							// Reset UI state on polling errors (e.g., job not found after restart)
							console.warn(`Polling failed for crawl job ${job.id}:`, error);
							servers = servers.map(s =>
								s.id === serverId ? { ...s, crawling: false, crawlJobId: undefined, crawlJobStatus: undefined } : s
							);
						}).finally(() => {
							// Always clean up crawling state when done
							servers = servers.map(s =>
								s.id === serverId ? { ...s, crawling: false, crawlJobId: undefined } : s
							);
						});
					}
				}
			} catch {
				// Ignore errors checking for jobs
			}
		}
	}

	async function resumeDownloadJobs() {
		// Check all datasets across all servers for running/pending download jobs
		for (const server of servers) {
			if (!server.datasets) continue;

			for (const dataset of server.datasets) {
				const datasetId = dataset.id;
				try {
					const res = await fetch(`/api/v1/download/datasets/${datasetId}/latest`);
					if (res.ok) {
						const job = await res.json();
						if (job && (job.status === 'running' || job.status === 'pending')) {
							// Resume polling this job
							fetchingDatasets[datasetId] = {
								progress: job.progress || 0,
								stage: job.current_stage || 'processing',
								jobId: job.id
							};
							fetchingDatasets = { ...fetchingDatasets };

							// Start polling
							pollJobStatus(
								`/api/v1/download/jobs/${job.id}`,
								(progressJob) => {
									fetchingDatasets[datasetId] = {
										progress: progressJob.progress || 0,
										stage: progressJob.current_stage || 'processing',
										jobId: job.id
									};
									fetchingDatasets = { ...fetchingDatasets };
								},
								{ interval: 2500, timeout: 600000 }
							).then((finalJob) => {
								// Job completed
								if (finalJob.status === 'completed') {
									console.log(`Download job ${job.id} completed for dataset ${datasetId}`);
									// Refresh datasets
									loadDatasets(server);
								} else if (finalJob.status === 'failed') {
									console.warn(`Download job ${job.id} failed:`, finalJob.error);
								}
							}).catch((error) => {
								// Reset UI state on polling errors
								console.warn(`Polling failed for download job ${job.id}:`, error);
							}).finally(() => {
								// Always clean up loading state when done
								delete fetchingDatasets[datasetId];
								fetchingDatasets = { ...fetchingDatasets };
							});
						}
					}
				} catch {
					// Ignore errors checking for jobs
				}
			}
		}
	}

	function addServer() {
		// Open modal instead of using prompt()
		showAddModal = true;
	}

	async function handleAddSave(e: any) {
		const payload = e.detail || {};
		// Ensure provider_type defaults to arcgis if not provided
		if (!payload.provider_type) payload.provider_type = 'arcgis';
		try {
			const response = await fetch('/api/v1/servers', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (!response.ok) throw new Error('Failed to add server');
			const newServer = await response.json();
			servers = [...servers, newServer];
			infoMessage = 'Server added';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error adding server: ' + (err instanceof Error ? err.message : String(err));
			showInfoModal = true;
		} finally {
			showAddModal = false;
		}
	}

	async function crawlServer(serverId: string) {
		try {
			// Set server as crawling
			servers = servers.map(s =>
				s.id === serverId ? { ...s, crawling: true, crawlJobStatus: null } : s
			);

			// Start crawl job
			const response = await fetch(`/api/v1/servers/${serverId}/crawl`, { method: 'POST' });
			if (!response.ok) throw new Error('Failed to start crawl');

			const job = await response.json();
			console.log('Crawl job started:', job);

			// Store job ID and start polling
			servers = servers.map(s =>
				s.id === serverId ? { ...s, crawlJobId: job.id, crawlJobStatus: job } : s
			);

			// Poll for progress
			try {
				const finalJob = await pollJobStatus(
					`/api/v1/servers/crawl/${job.id}`,
					(progressJob) => {
						// Update UI with progress
						servers = servers.map(s =>
							s.id === serverId ? { ...s, crawlJobStatus: progressJob } : s
						);
					},
					{ interval: 2500, timeout: 600000 }  // 10 minute timeout for large servers
				);

				// Job completed - refresh dataset list
				if (finalJob.status === 'completed') {
					infoMessage = `Crawl complete: ${finalJob.datasets_new} new, ${finalJob.datasets_updated} updated`;
					showInfoModal = true;

					// Refresh datasets for this server if expanded
					const server = servers.find(s => s.id === serverId);
					if (server?.expanded) {
						await refreshServerDatasets(serverId);
					}

					// Reload servers list to update last_crawl timestamp
					await loadServers();
				} else if (finalJob.status === 'failed') {
					infoMessage = `Crawl failed: ${finalJob.error}`;
					showInfoModal = true;
				}
			} finally {
				// Clear crawling state
				servers = servers.map(s =>
					s.id === serverId ? { ...s, crawling: false, crawlJobId: undefined, crawlJobStatus: undefined } : s
				);
			}
		} catch (e) {
			servers = servers.map(s =>
				s.id === serverId ? { ...s, crawling: false } : s
			);
			infoMessage = 'Error crawling server: ' + (e instanceof Error ? e.message : 'Unknown error');
			showInfoModal = true;
		}
	}

	async function cancelCrawl(serverId: string) {
		const server = servers.find(s => s.id === serverId);
		if (!server?.crawlJobId) return;

		try {
			// Cancel the job on backend
			const res = await fetch(`/api/v1/servers/crawl/${server.crawlJobId}/cancel`, {
				method: 'POST'
			});

			if (!res.ok) throw new Error('Failed to cancel crawl');

			// Reset UI state immediately
			servers = servers.map(s =>
				s.id === serverId ? { ...s, crawling: false, crawlJobId: undefined, crawlJobStatus: null } : s
			);

			infoMessage = 'Crawl cancelled';
			showInfoModal = true;
		} catch (err) {
			infoMessage = 'Error cancelling crawl: ' + (err instanceof Error ? err.message : String(err));
			showInfoModal = true;
		}
	}

	async function refreshServerDatasets(serverId: string) {
		try {
			const res = await fetch(`/api/v1/datasets?geoserver_id=${serverId}&limit=1000`);
			if (!res.ok) throw new Error('Failed to refresh datasets');
			const datasets = await res.json();

			servers = servers.map(s =>
				s.id === serverId ? { ...s, datasets } : s
			);
		} catch (err) {
			console.error('Failed to refresh datasets:', err);
		}
	}

		function openEdit(server: Server) {
			serverBeingEdited = server;
			editInitial = { name: server.name, base_url: server.base_url, country: server.country };
			showEditModal = true;
		}

		async function handleEditSave(e: any) {
			if (!serverBeingEdited) return;
			const payload = e.detail || {};
			try {
				const res = await fetch(`/api/v1/servers/${serverBeingEdited.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
				if (!res.ok) throw new Error('Failed to update server');
				const updated = await res.json();
				servers = servers.map(s => s.id === serverBeingEdited!.id ? { ...s, ...updated } : s);
				infoMessage = 'Server updated'; showInfoModal = true;
			} catch (err) {
				infoMessage = 'Error updating server: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
			} finally {
				showEditModal = false; serverBeingEdited = null;
			}
		}

		function confirmDelete(server: Server) {
			serverToDelete = server;
			showConfirmDelete = true;
		}

		async function handleDeleteConfirm() {
			if (!serverToDelete) return;
			try {
				const res = await fetch(`/api/v1/servers/${serverToDelete.id}`, { method: 'DELETE' });
				if (!res.ok && res.status !== 204) throw new Error('Failed to delete');
				servers = servers.filter(s => s.id !== serverToDelete!.id);
				infoMessage = 'Server deleted'; showInfoModal = true;
			} catch (err) {
				infoMessage = 'Error deleting server: ' + (err instanceof Error ? err.message : String(err)); showInfoModal = true;
			} finally {
				showConfirmDelete = false; serverToDelete = null;
			}
		}

		async function loadDatasets(server: Server) {
			server.loading = true;
			try {
				const res = await fetch(`/api/v1/datasets?geoserver_id=${server.id}&limit=1000`);
				if (!res.ok) throw new Error('Failed to fetch datasets');
				server.datasets = await res.json();
			} catch (err) {
				infoMessage = 'Error loading datasets: ' + (err instanceof Error ? err.message : String(err));
				showInfoModal = true;
			} finally {
				server.loading = false;
			}
			servers = [...servers];
		}

		async function toggleServer(server: any) {
			if (!server.expanded && !server.datasets) {
				await loadDatasets(server);
			}
			server.expanded = !server.expanded;
			servers = [...servers];
		}

		async function cancelFetch(datasetId: string) {
			const fetchInfo = fetchingDatasets[datasetId];
			if (!fetchInfo?.jobId) return;

			try {
				const res = await fetch(`/api/v1/download/jobs/${fetchInfo.jobId}/cancel`, {
					method: 'POST'
				});

				if (!res.ok) throw new Error('Failed to cancel download');

				console.log(`Download job ${fetchInfo.jobId} cancelled`);

				// Reset UI state immediately
				delete fetchingDatasets[datasetId];
				fetchingDatasets = { ...fetchingDatasets };
			} catch (err) {
				console.error('Error cancelling download:', err);
				infoMessage = 'Error cancelling: ' + (err instanceof Error ? err.message : String(err));
				showInfoModal = true;
			}
		}

		async function fetchDataset(dataset: any, e?: Event) {
			e && e.stopPropagation();

			// Set loading state with initial progress
			fetchingDatasets[dataset.id] = { progress: 0, stage: 'starting' };
			fetchingDatasets = { ...fetchingDatasets };

			try {
				// Start fetch & cache job
				console.log(`Starting fetch job for dataset ${dataset.id}...`);

				const res = await fetch('/api/v1/download', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ dataset_ids: [dataset.id], format: 'geojson', force_refresh: true })
				});

				if (!res.ok) {
					const errorText = await res.text();
					console.error('Failed to start fetch job:', errorText);
					throw new Error(`Failed to start fetch (${res.status}): ${errorText}`);
				}

				const data = await res.json();
				console.log('Download job response:', data);

				if (data.job_id) {
					// Job was created, poll for progress
					console.log(`Polling download job ${data.job_id}...`);

					try {
						const finalJob = await pollJobStatus(
							`/api/v1/download/jobs/${data.job_id}`,
							(progressJob) => {
								// Update UI with progress
								fetchingDatasets[dataset.id] = {
									progress: progressJob.progress || 0,
									stage: progressJob.current_stage || 'processing',
									jobId: data.job_id
								};
								fetchingDatasets = { ...fetchingDatasets };
							},
							{ interval: 2500, timeout: 600000 }
						);

						// Job completed
						if (finalJob.status === 'completed') {
							infoMessage = `${dataset.name} cached successfully!`;
							showInfoModal = true;

							// Refresh the server's datasets to update cached status
							const server = servers.find(s => s.datasets?.some(d => d.id === dataset.id));
							if (server) {
								await loadDatasets(server);
							}
						} else if (finalJob.status === 'failed') {
							throw new Error(finalJob.error || 'Download job failed');
						}
					} catch (pollErr) {
						console.error('Error polling download job:', pollErr);
						throw pollErr;
					}
				} else if (data.download_url) {
					// Direct download URL returned - already cached
					infoMessage = `${dataset.name} already cached!`;
					showInfoModal = true;
					// Refresh the server's datasets to update cached status
					const server = servers.find(s => s.datasets?.some(d => d.id === dataset.id));
					if (server) {
						await loadDatasets(server);
					}
				}
			} catch (err) {
				console.error('Error in fetchDataset:', err);
				infoMessage = 'Error: ' + (err instanceof Error ? err.message : String(err));
				showInfoModal = true;
			} finally {
				// Clear loading state
				delete fetchingDatasets[dataset.id];
				fetchingDatasets = { ...fetchingDatasets };
			}
		}

		async function showOnMap(dataset: any, e?: Event) {
			e && e.stopPropagation();
			try {
				// Only work with cached datasets (must have PostGIS cache_table for tiles)
				if (!dataset.is_cached || !dataset.cache_table) {
					infoMessage = 'Please fetch and cache the dataset first using the refresh button.';
					showInfoModal = true;
					return;
				}

				console.log(`Adding dataset ${dataset.id} to map...`);

				// Add vector tiles to map from PostGIS cache
				mapStore.addLayer(dataset.id, dataset.name, dataset.cache_table, dataset.geometry_type, martinUrl);

				// Parse bbox WKT and zoom to extent
				if (dataset.bbox && $mapStore.map) {
					try {
						// Parse WKT POLYGON to extract coordinates
						// Format: POLYGON((minx miny, maxx miny, maxx maxy, minx maxy, minx miny))
						const coordsMatch = dataset.bbox.match(/POLYGON\(\(([^)]+)\)\)/);
						if (coordsMatch) {
							const coords = coordsMatch[1].split(',').map((pair: string) => {
								const [x, y] = pair.trim().split(' ').map(parseFloat);
								return [x, y];
							});

							// Extract bounds (min/max of all coordinates)
							const lons = coords.map((c: number[]) => c[0]);
							const lats = coords.map((c: number[]) => c[1]);
							const bounds: [[number, number], [number, number]] = [
								[Math.min(...lons), Math.min(...lats)],
								[Math.max(...lons), Math.max(...lats)]
							];

							// Zoom to bounds
							$mapStore.map.fitBounds(bounds, { padding: 50 });
						}
					} catch (err) {
						console.error('Failed to parse bbox or zoom to extent:', err);
					}
				}

				infoMessage = `${dataset.name} loaded on map!`;
				showInfoModal = true;
			} catch (err) {
				console.error('Error in showOnMap:', err);
				infoMessage = 'Error: ' + (err instanceof Error ? err.message : String(err));
				showInfoModal = true;
			}
		}

		async function downloadDatasetFile(dataset: any, e?: Event) {
			e && e.stopPropagation();
			try {
				if (!dataset.is_cached) {
					infoMessage = 'Please fetch and cache the dataset first using the play button.';
					showInfoModal = true;
					return;
				}

				console.log(`Downloading dataset file ${dataset.id}...`);
				const res = await fetch(`/api/v1/download/${dataset.id}/file`);
				if (!res.ok) {
					const errorText = await res.text();
					console.error('Download failed:', errorText);
					throw new Error(`Failed to download (${res.status}): ${errorText}`);
				}

				// Check content type to ensure we got the file
				const contentType = res.headers.get('content-type');
				console.log('Downloaded file content-type:', contentType);

				const blob = await res.blob();
				console.log('Downloaded blob size:', blob.size, 'bytes');

				const url = window.URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `${dataset.name || 'dataset'}.geojson`;
				document.body.appendChild(a);
				a.click();
				a.remove();
				window.URL.revokeObjectURL(url);

				infoMessage = `Downloaded ${dataset.name} (${(blob.size / 1024).toFixed(2)} KB)`;
				showInfoModal = true;
			} catch (err) {
				console.error('Error in downloadDatasetFile:', err);
				infoMessage = 'Error downloading file: ' + (err instanceof Error ? err.message : String(err));
				showInfoModal = true;
			}
		}

	function formatExtent(extent: any): string {
		if (!extent || !extent.coordinates) return 'N/A';
		try {
			const coords = extent.coordinates[0];
			if (!coords || coords.length < 2) return 'N/A';
			const [[minX, minY], [maxX, maxY]] = [coords[0], coords[2]];
			return `[${minX.toFixed(2)}, ${minY.toFixed(2)}, ${maxX.toFixed(2)}, ${maxY.toFixed(2)}]`;
		} catch {
			return 'N/A';
		}
	}

	function showServerDetails(server: Server) {
		detailModalTitle = `Server: ${server.name}`;
		detailModalRows = [
			{ label: 'Type', value: server.provider_type },
			{ label: 'Country', value: server.country || 'N/A' },
			{ label: 'URL', value: server.base_url, link: true },
			{ label: 'Datasets', value: String(server.dataset_count || 0) },
			{ label: 'Status', value: server.health_status || 'Unknown' },
			{ label: 'Last Crawl', value: server.last_crawl ? new Date(server.last_crawl).toLocaleString() : 'Never' }
		];
		showDetailModal = true;
	}

	function showDatasetDetails(dataset: any) {
		detailModalTitle = `Dataset: ${dataset.name}`;
		detailModalRows = [];

		if (dataset.access_url) {
			detailModalRows.push({ label: 'Access URL', value: dataset.access_url, link: true });
		}
		if (dataset.url) {
			detailModalRows.push({ label: 'URL', value: dataset.url, link: true });
		}
		detailModalRows.push(
			{ label: 'Features', value: dataset.feature_count?.toLocaleString() || 'N/A' }
		);
		if (dataset.geometry_type) {
			detailModalRows.push({ label: 'Geometry Type', value: dataset.geometry_type });
		}
		if (dataset.source_srid) {
			detailModalRows.push({ label: 'Source SRID', value: String(dataset.source_srid) });
		}
		if (dataset.bbox) {
			detailModalRows.push({ label: 'Bbox', value: dataset.bbox.substring(0, 100) + (dataset.bbox.length > 100 ? '...' : '') });
		}
		if (dataset.themes && dataset.themes.length > 0) {
			detailModalRows.push({ label: 'Themes', value: dataset.themes.join(', ') });
		}
		if (dataset.keywords && dataset.keywords.length > 0) {
			detailModalRows.push({ label: 'Keywords', value: dataset.keywords.join(', ') });
		}
		if (dataset.last_fetched_at) {
			detailModalRows.push({ label: 'Last Fetched', value: new Date(dataset.last_fetched_at).toLocaleString() });
		}
		if (dataset.is_cached) {
			detailModalRows.push({ label: 'Cache Status', value: 'Cached ✓' });
		}

		showDetailModal = true;
	}

</script>

<div class="servers-tab">
	<div class="header">
		<h3>Geoservers</h3>
		<button class="add-btn" on:click={addServer}>
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<line x1="12" y1="5" x2="12" y2="19"></line>
				<line x1="5" y1="12" x2="19" y2="12"></line>
			</svg>
			Add Server
		</button>
	</div>

	<!-- Global Dataset Search -->
	<div class="global-search-section">
		<input
			type="text"
			class="global-search-input"
			placeholder="Search all datasets (name, theme, keyword)..."
			bind:value={globalDatasetSearch}
		/>
	</div>

	<!-- Server Filters (collapsible) -->
	<details class="server-filters-details">
		<summary>Server Filters</summary>
		<div class="filters">
			<select bind:value={filterCountry} class="filter-select">
				<option value="">All Countries</option>
				{#each countries as country}
					<option value={country}>{country}</option>
				{/each}
			</select>
			<select bind:value={filterServerType} class="filter-select">
				<option value="">All Types</option>
				{#each serverTypes as type}
					<option value={type}>{type}</option>
				{/each}
			</select>
			<select bind:value={filterHealthStatus} class="filter-select">
				<option value="">All Status</option>
				{#each healthStatuses as status}
					<option value={status}>{status}</option>
				{/each}
			</select>
			<select bind:value={sortBy} class="filter-select">
				<option value="">No Sort</option>
				<option value="name">Sort by Name</option>
				<option value="country">Sort by Country</option>
			</select>
			{#if sortBy}
				<button class="sort-direction-btn" on:click={() => sortAscending = !sortAscending} title={sortAscending ? 'Ascending' : 'Descending'}>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						{#if sortAscending}
							<line x1="12" y1="19" x2="12" y2="5"></line>
							<polyline points="5 12 12 5 19 12"></polyline>
						{:else}
							<line x1="12" y1="5" x2="12" y2="19"></line>
							<polyline points="5 12 12 19 19 12"></polyline>
						{/if}
					</svg>
				</button>
			{/if}
		</div>
	</details>

	<!-- Modals -->
	<ServerForm open={showAddModal} mode="add" on:save={handleAddSave} on:close={() => showAddModal = false} />
	<ServerForm open={showEditModal} initial={editInitial} mode="edit" on:save={handleEditSave} on:close={() => { showEditModal = false; serverBeingEdited = null; }} />
	<ConfirmModal open={showConfirmDelete} title="Delete Server" message={serverToDelete ? `Delete server "${serverToDelete.name}"? This will remove its datasets from the catalogue.` : ''} on:confirm={handleDeleteConfirm} on:close={() => { showConfirmDelete = false; serverToDelete = null; }} />
	<InfoModal open={showInfoModal} message={infoMessage} on:close={() => showInfoModal = false} />
	<InfoDetailModal open={showDetailModal} title={detailModalTitle} rows={detailModalRows} on:close={() => showDetailModal = false} />

	{#if loading}
		<div class="loading">Loading servers...</div>
	{:else if error}
		<div class="error">{error}</div>
	{:else if servers.length === 0}
		<div class="empty">No servers configured. Click "Add Server" to get started.</div>
	{:else}
		<!-- Server Management View -->
		<div class="server-list" class:grid-view={useGridView}>
			{#each filteredServers as server}
				<div class="server-card" class:expanded={server.expanded} on:click={() => toggleServer(server)}>
					<div class="server-header">
						<div class="server-info">
							<h4>{server.name}</h4>
							<button class="icon-btn server-info-btn tooltip-trigger" on:click|stopPropagation={() => showServerDetails(server)} data-tooltip="View Details">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<circle cx="12" cy="12" r="10"></circle>
									<line x1="12" y1="16" x2="12" y2="12"></line>
									<line x1="12" y1="8" x2="12.01" y2="8"></line>
								</svg>
							</button>
						</div>
						<div class="server-actions">
							{#if server.crawling}
								<button
									class="icon-btn cancel-btn tooltip-trigger"
									on:click|stopPropagation={() => cancelCrawl(server.id)}
									data-tooltip={server.crawlJobStatus ? formatJobProgress(server.crawlJobStatus) : 'Starting crawl...'}>
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<circle cx="12" cy="12" r="10"></circle>
										<line x1="15" y1="9" x2="9" y2="15"></line>
										<line x1="9" y1="9" x2="15" y2="15"></line>
									</svg>
								</button>
							{:else}
								<button
									class="icon-btn crawl-btn tooltip-trigger"
									on:click|stopPropagation={() => crawlServer(server.id)}
									data-tooltip="Crawl server for datasets">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<polygon points="5 3 19 12 5 21 5 3"></polygon>
									</svg>
								</button>
							{/if}
							<button class="icon-btn edit-btn tooltip-trigger" on:click|stopPropagation={() => openEdit(server)} data-tooltip="Edit server">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
									<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
								</svg>
							</button>
							<button class="icon-btn delete-btn tooltip-trigger" on:click|stopPropagation={() => confirmDelete(server)} data-tooltip="Delete server">
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<polyline points="3 6 5 6 21 6"></polyline>
									<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
								</svg>
							</button>
						</div>
					</div>

					{#if server.expanded}
						<div class="datasets-section" on:click|stopPropagation>
							{#if server.loading}
								<div class="datasets-loading">Loading datasets...</div>
							{:else if server.datasets && server.datasets.length > 0}
								{@const filteredAndSortedDatasets = sortDatasetsByCached(filterDatasetsBySearch(server.datasets))}
								{#if filteredAndSortedDatasets.length === 0}
									<div class="datasets-empty">No datasets match your search</div>
								{:else}
							<div class="dataset-list">
									{#each filteredAndSortedDatasets as dataset}
										<div class="dataset-card" class:cached={dataset.is_cached}>
											<div class="dataset-row">
												<div class="dataset-info">
													<div class="dataset-title-row">
														<span class="dataset-name">{dataset.name}</span>
														{#if dataset.is_cached}
															<span class="cached-check" title="Cached and ready">✓</span>
														{/if}
													</div>
													<div class="dataset-meta">
														{#if dataset.feature_count}
															<span class="badge feature-badge">{dataset.feature_count.toLocaleString()}</span>
														{/if}
														{#if dataset.themes && dataset.themes.length > 0}
															{#each dataset.themes.slice(0, 2) as theme}
																<span class="badge theme-badge">{theme.replace(/_/g, ' ')}</span>
															{/each}
														{/if}
														{#if dataset.geometry_type}
															<span class="badge geom-badge">{dataset.geometry_type}</span>
														{/if}
													</div>
												</div>
												<div class="dataset-actions">
													<button class="icon-btn info-btn tooltip-trigger" on:click|stopPropagation={() => showDatasetDetails(dataset)} data-tooltip="View Details">
														<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<circle cx="12" cy="12" r="10"></circle>
															<line x1="12" y1="16" x2="12" y2="12"></line>
															<line x1="12" y1="8" x2="12.01" y2="8"></line>
														</svg>
													</button>
													{#if fetchingDatasets[dataset.id]}
														<button
															class="icon-btn cancel-btn tooltip-trigger"
															on:click|stopPropagation={() => cancelFetch(dataset.id)}
															data-tooltip={fetchingDatasets[dataset.id]
																? `${fetchingDatasets[dataset.id].stage || 'fetching'}: ${Math.round(fetchingDatasets[dataset.id].progress || 0)}%`
																: "Cancel"}
														>
															<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
																<line x1="18" y1="6" x2="6" y2="18"></line>
																<line x1="6" y1="6" x2="18" y2="18"></line>
															</svg>
														</button>
													{:else}
														<button
															class="icon-btn fetch-btn tooltip-trigger"
															on:click|stopPropagation={(e) => fetchDataset(dataset, e)}
															data-tooltip="Fetch & Cache"
														>
															<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
																<path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
															</svg>
														</button>
													{/if}
													<button
														class="icon-btn map-btn tooltip-trigger"
														on:click|stopPropagation={(e) => showOnMap(dataset, e)}
														disabled={!dataset.is_cached}
														data-tooltip={dataset.is_cached ? 'Show on Map' : 'Cache dataset first'}
													>
														<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4-7 4z"></path>
															<line x1="8" y1="2" x2="8" y2="18"></line>
															<line x1="16" y1="6" x2="16" y2="22"></line>
														</svg>
													</button>
													<button
														class="icon-btn download-btn tooltip-trigger"
														on:click|stopPropagation={(e) => downloadDatasetFile(dataset, e)}
														disabled={!dataset.is_cached}
														data-tooltip={dataset.is_cached ? 'Download File' : 'Cache dataset first'}
													>
														<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
															<polyline points="7 10 12 15 17 10"></polyline>
															<line x1="12" y1="15" x2="12" y2="3"></line>
														</svg>
													</button>
												</div>
											</div>
										</div>
									{/each}
								</div>
								{/if}
							{:else}
								<div class="datasets-empty">No datasets. Try crawling the server.</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.servers-tab {
		display: flex;
		flex-direction: column;
		gap: 16px;
		overflow: visible;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
	}

	.add-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 16px;
		border: none;
		background: var(--text-primary);
		color: white;
		border-radius: 8px;
		cursor: pointer;
		font-size: 14px;
		transition: opacity 0.2s;
	}

	.add-btn:hover {
		opacity: 0.8;
	}

	.loading,
	.error,
	.empty {
		padding: 24px;
		text-align: center;
		color: var(--text-secondary);
	}

	.error {
		color: #dc2626;
	}

	.server-list {
		display: flex;
		flex-direction: column;
		gap: 12px;
		overflow: visible;
	}

	.server-card {
		background: white;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 12px;
		overflow: visible;
		transition: all 0.2s;
		cursor: pointer;
	}

	.server-card:hover {
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		background: rgba(0, 0, 0, 0.01);
	}

	.server-card.expanded {
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
	}

	.server-header {
		padding: 10px 12px;
		display: flex;
		gap: 8px;
		align-items: center;
	}

	.server-info {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 6px;
	}

	h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}


	.badge {
		padding: 2px 6px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 3px;
		font-size: 10px;
		text-transform: uppercase;
		font-weight: 500;
		white-space: nowrap;
	}

	.feature-badge {
		background: rgba(59, 130, 246, 0.1);
		color: #3b82f6;
		font-weight: 600;
	}

	.icon-btn {
		width: 28px;
		height: 28px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.15);
		background: white;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		flex-shrink: 0;
	}

	.icon-btn:hover:not(:disabled) {
		background: rgba(0, 0, 0, 0.05);
		border-color: rgba(0, 0, 0, 0.25);
	}

	.icon-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
		background: rgba(0, 0, 0, 0.02);
	}

	.delete-btn {
		border-color: #fca5a5;
		color: #dc2626;
	}

	.cancel-btn {
		border-color: #fed7aa;
		color: #ea580c;
	}

	.cancel-btn:hover:not(:disabled) {
		background: #fff7ed;
		border-color: #fb923c;
	}

	.delete-btn:hover {
		background: #fee;
		border-color: #dc2626;
	}

	.map-btn {
		border-color: #3b82f6;
		color: #3b82f6;
	}

	.map-btn:hover {
		background: rgba(59, 130, 246, 0.1);
	}

	.server-actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		position: relative;
		z-index: 10;
	}

	.datasets-section {
		margin-top: 12px;
		width: 100%;
	}

	.datasets-loading,
	.datasets-empty {
		padding: 12px;
		text-align: center;
		color: var(--text-secondary);
		font-size: 13px;
	}

	.dataset-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.dataset-card {
		background: rgba(0, 0, 0, 0.02);
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-radius: 6px;
		transition: all 0.2s;
	}

	.dataset-card.cached {
		background: rgba(34, 197, 94, 0.05);
		border-color: rgba(34, 197, 94, 0.2);
	}

	.dataset-card:hover {
		background: rgba(0, 0, 0, 0.04);
		border-color: rgba(0, 0, 0, 0.15);
	}

	.dataset-card.cached:hover {
		background: rgba(34, 197, 94, 0.08);
	}

	.dataset-row {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 8px;
	}

	.dataset-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.dataset-title-row {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.dataset-name {
		flex: 1;
		font-size: 12px;
		font-weight: 500;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
	}

	.cached-check {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 16px;
		height: 16px;
		background: #22c55e;
		color: white;
		border-radius: 50%;
		font-size: 10px;
		font-weight: bold;
		flex-shrink: 0;
	}

	.dataset-meta {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}

	.theme-badge {
		background: rgba(59, 130, 246, 0.1);
		color: #2563eb;
	}

	.geom-badge {
		background: rgba(168, 85, 247, 0.1);
		color: #7c3aed;
	}

	.dataset-actions {
		display: flex;
		gap: 4px;
		flex-shrink: 0;
	}

	/* Dataset Controls */
	.dataset-controls {
		display: flex;
		gap: 8px;
		padding: 8px;
		margin-bottom: 8px;
		background: rgba(0, 0, 0, 0.02);
		border-radius: 6px;
		align-items: center;
	}

	.dataset-search {
		flex: 1;
		padding: 6px 10px;
		border: 1px solid rgba(0, 0, 0, 0.15);
		border-radius: 6px;
		background: white;
		font-size: 12px;
		color: var(--text-primary);
		transition: all 0.2s;
	}

	.dataset-search:hover {
		border-color: rgba(0, 0, 0, 0.25);
	}

	.dataset-search:focus {
		outline: none;
		border-color: var(--text-primary);
	}

	.dataset-search::placeholder {
		color: var(--text-secondary);
	}

	.sort-checkbox {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 12px;
		color: var(--text-primary);
		cursor: pointer;
		white-space: nowrap;
		user-select: none;
	}

	.sort-checkbox input[type="checkbox"] {
		cursor: pointer;
		width: 14px;
		height: 14px;
	}

	/* Filters and Sorting */
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-bottom: 16px;
		padding: 0 0 12px 0;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.filter-select {
		flex: 1;
		min-width: 120px;
		padding: 6px 10px;
		border: 1px solid rgba(0, 0, 0, 0.15);
		border-radius: 6px;
		background: white;
		font-size: 12px;
		color: var(--text-primary);
		cursor: pointer;
		transition: all 0.2s;
	}

	.filter-select:hover {
		border-color: rgba(0, 0, 0, 0.25);
	}

	.filter-select:focus {
		outline: none;
		border-color: var(--text-primary);
	}

	.sort-direction-btn {
		width: 32px;
		height: 32px;
		padding: 0;
		border: 1px solid rgba(0, 0, 0, 0.15);
		background: white;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
	}

	.sort-direction-btn:hover {
		background: rgba(0, 0, 0, 0.05);
		border-color: rgba(0, 0, 0, 0.25);
	}

	/* Custom Tooltips */
	.tooltip-trigger {
		position: relative;
	}

	.tooltip-trigger::before {
		content: attr(data-tooltip);
		position: absolute;
		bottom: calc(100% + 8px);
		left: 50%;
		transform: translateX(-50%);
		padding: 8px 12px;
		background: rgba(0, 0, 0, 0.9);
		color: white;
		font-size: 13px;
		font-weight: 500;
		line-height: 1.4;
		border-radius: 6px;
		white-space: nowrap;
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.2s ease-in-out;
		z-index: 1000;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
	}

	.tooltip-trigger::after {
		content: '';
		position: absolute;
		bottom: calc(100% + 2px);
		left: 50%;
		transform: translateX(-50%);
		border: 6px solid transparent;
		border-top-color: rgba(0, 0, 0, 0.9);
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.2s ease-in-out;
		z-index: 1000;
	}

	.tooltip-trigger:hover::before,
	.tooltip-trigger:hover::after {
		opacity: 1;
	}

	/* Grid View */
	.server-list.grid-view {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 12px;
	}

	.server-list.grid-view .server-card {
		height: fit-content;
	}

	/* Spinner animation */
	.spinner {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	.fetch-btn.loading {
		opacity: 0.7;
		cursor: wait;
	}

	/* Global Search Section */
	.global-search-section {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-bottom: 16px;
		padding-bottom: 16px;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.global-search-input {
		width: 100%;
		padding: 10px 12px;
		border: 1px solid rgba(0, 0, 0, 0.15);
		border-radius: 8px;
		background: white;
		font-size: 14px;
		color: var(--text-primary);
		transition: all 0.2s;
	}

	.global-search-input:hover {
		border-color: rgba(0, 0, 0, 0.25);
	}

	.global-search-input:focus {
		outline: none;
		border-color: var(--text-primary);
		box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.05);
	}

	.global-search-input::placeholder {
		color: var(--text-secondary);
	}

	/* Server Filters Collapsible */
	.server-filters-details {
		margin-bottom: 16px;
		border: 1px solid rgba(0, 0, 0, 0.1);
		border-radius: 8px;
		background: white;
	}

	.server-filters-details summary {
		padding: 12px;
		cursor: pointer;
		font-size: 13px;
		font-weight: 600;
		color: var(--text-primary);
		list-style: none;
		display: flex;
		align-items: center;
		gap: 8px;
		transition: background 0.2s;
	}

	.server-filters-details summary:hover {
		background: rgba(0, 0, 0, 0.02);
	}

	.server-filters-details summary::-webkit-details-marker {
		display: none;
	}

	.server-filters-details[open] summary {
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.server-filters-details .filters {
		margin: 12px;
		margin-bottom: 0;
		padding-bottom: 0;
		border-bottom: none;
	}

	/* Global Datasets Section */
	.global-datasets-section {
		margin-bottom: 20px;
	}

	.section-title {
		margin: 0 0 12px 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.empty-results {
		padding: 32px 16px;
		text-align: center;
		color: var(--text-secondary);
		font-size: 13px;
	}

	.dataset-card.global {
		margin-bottom: 8px;
	}

	.dataset-source {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 4px 8px;
		background: rgba(0, 0, 0, 0.03);
		border-bottom: 1px solid rgba(0, 0, 0, 0.08);
		flex-wrap: wrap;
	}

	.server-badge {
		background: rgba(99, 102, 241, 0.1);
		color: #4f46e5;
		font-weight: 600;
	}

	.country-badge {
		background: rgba(245, 158, 11, 0.1);
		color: #d97706;
	}
</style>
