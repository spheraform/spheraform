<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Modal from './Modal.svelte';

  export let open: boolean = false;
  export let initial: { name?: string; base_url?: string; country?: string } | null = {};
  export let mode: 'add' | 'edit' = 'add';

  const dispatch = createEventDispatcher();

  let name = initial?.name ?? '';
  let base_url = initial?.base_url ?? '';
  let country = initial?.country ?? '';

  // Re-populate form when opened or when initial data changes
  $: if (open) {
    name = initial?.name ?? '';
    base_url = initial?.base_url ?? '';
    country = initial?.country ?? '';
  }

  function onSave() {
    dispatch('save', { name: name.trim(), base_url: base_url.trim(), country: country.trim() || null });
  }

  function onClose() {
    dispatch('close');
  }
</script>

<Modal {open} title={mode === 'add' ? 'Add Server' : 'Edit Server'} on:close={onClose}>
  <div class="form-row">
    <label>Name</label>
    <input bind:value={name} placeholder="Display name" />
  </div>
  <div class="form-row">
    <label>Base URL</label>
    <input bind:value={base_url} placeholder="https://example.com/server/rest/services" />
  </div>
  <div class="form-row">
    <label>Country (optional)</label>
    <input bind:value={country} placeholder="US, GB, etc." />
  </div>
  <div class="actions">
    <button on:click={onSave} class="save">Save</button>
    <button on:click={onClose} class="cancel">Cancel</button>
  </div>
</Modal>

<style>
  .form-row { display:flex;flex-direction:column;gap:6px;margin-bottom:10px }
  label { font-size:13px;color:var(--text-secondary) }
  input { padding:8px;border:1px solid rgba(0,0,0,0.12);border-radius:6px }
  .actions { display:flex;gap:8px;justify-content:flex-end;margin-top:8px }
  .save{background:var(--text-primary);color:#fff;padding:8px 12px;border-radius:6px;border:none}
  .cancel{background:#fff;border:1px solid rgba(0,0,0,0.08);padding:8px 12px;border-radius:6px}
</style>
