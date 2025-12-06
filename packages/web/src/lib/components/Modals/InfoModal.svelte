<script lang="ts">
  import Modal from './Modal.svelte';
  import { createEventDispatcher } from 'svelte';
  export let open = false;
  export let title = 'Info';
  export let message = '';
  const dispatch = createEventDispatcher();
  function onClose(){ dispatch('close'); }
</script>

<Modal {open} {title} on:close={onClose}>
  <div style="white-space:pre-wrap">{message}</div>
  <div style="display:flex;justify-content:flex-end;margin-top:12px">
    <button on:click={onClose} class="ok">OK</button>
  </div>
</Modal>

<style>
  .ok{background:var(--text-primary);color:#fff;padding:8px 12px;border-radius:6px;border:none}
</style>
