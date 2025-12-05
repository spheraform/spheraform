<script lang="ts">
  import Modal from './Modal.svelte';
  import { createEventDispatcher } from 'svelte';
  export let open = false;
  export let title = 'Confirm';
  export let message = '';
  const dispatch = createEventDispatcher();
  function onConfirm(){ dispatch('confirm'); }
  function onClose(){ dispatch('close'); }
</script>

<Modal {open} {title} on:close={onClose}>
  <div style="margin-bottom:12px">{message}</div>
  <div style="display:flex;gap:8px;justify-content:flex-end">
    <button on:click={onConfirm} class="confirm">Yes</button>
    <button on:click={onClose} class="cancel">No</button>
  </div>
</Modal>

<style>
  .confirm{background:#dc2626;color:#fff;padding:8px 12px;border-radius:6px;border:none}
  .cancel{background:#fff;border:1px solid rgba(0,0,0,0.08);padding:8px 12px;border-radius:6px}
</style>
