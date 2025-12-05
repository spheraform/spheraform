<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  export let open: boolean = false;
  export let title: string = '';
  const dispatch = createEventDispatcher();

  function close() {
    dispatch('close');
  }
</script>

{#if open}
  <div class="modal-backdrop" on:click={close}>
    <div class="modal" on:click|stopPropagation>
      <div class="modal-header">
        <h3>{title}</h3>
        <button class="close" on:click={close}>✕</button>
      </div>
      <div class="modal-body">
        <slot />
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal {
    background: white;
    border-radius: 8px;
    width: 480px;
    max-width: 92%;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
    overflow: hidden;
  }
  .modal-header {
    display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid rgba(0,0,0,0.06);
  }
  .modal-body { padding: 16px; }
  .close { background: none;border: none;font-size:16px;cursor:pointer }
</style>
