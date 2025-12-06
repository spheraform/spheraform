<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let open = false;
	export let title = 'Details';
	export let rows: Array<{ label: string; value: string; link?: boolean }> = [];

	const dispatch = createEventDispatcher();

	function close() {
		dispatch('close');
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			close();
		}
	}
</script>

{#if open}
	<div class="modal-backdrop" on:click={handleBackdropClick}>
		<div class="modal">
			<div class="modal-header">
				<h3>{title}</h3>
				<button class="close-btn" on:click={close} aria-label="Close">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<line x1="18" y1="6" x2="6" y2="18"></line>
						<line x1="6" y1="6" x2="18" y2="18"></line>
					</svg>
				</button>
			</div>
			<div class="modal-body">
				{#each rows as row}
					<div class="info-row">
						<strong>{row.label}:</strong>
						{#if row.link && row.value}
							<a href={row.value} target="_blank" rel="noopener noreferrer">{row.value}</a>
						{:else}
							<span>{row.value || 'N/A'}</span>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 10001;
	}

	.modal {
		background: white;
		border-radius: 12px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
		max-width: 600px;
		width: 90%;
		max-height: 80vh;
		display: flex;
		flex-direction: column;
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 20px 24px;
		border-bottom: 1px solid rgba(0, 0, 0, 0.1);
	}

	.modal-header h3 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.close-btn {
		width: 32px;
		height: 32px;
		border: none;
		background: none;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		transition: background 0.2s;
		color: var(--text-secondary);
	}

	.close-btn:hover {
		background: rgba(0, 0, 0, 0.05);
		color: var(--text-primary);
	}

	.modal-body {
		padding: 24px;
		overflow-y: auto;
	}

	.info-row {
		margin-bottom: 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.info-row:last-child {
		margin-bottom: 0;
	}

	.info-row strong {
		color: var(--text-primary);
		font-weight: 600;
		font-size: 13px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.info-row span {
		color: var(--text-primary);
		font-size: 14px;
		word-break: break-word;
	}

	.info-row a {
		color: #3b82f6;
		text-decoration: none;
		font-size: 14px;
		word-break: break-all;
		transition: color 0.2s;
	}

	.info-row a:hover {
		color: #2563eb;
		text-decoration: underline;
	}
</style>
