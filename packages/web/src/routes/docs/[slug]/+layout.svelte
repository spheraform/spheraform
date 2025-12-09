<script lang="ts">
  const docs = [
    { slug: 'api', title: 'API Docs' },
    { slug: 'about', title: 'About' },
    { slug: 'settings', title: 'Settings' }
  ];
</script>

<div class="docs-layout">
  <aside class="sidebar">
    <div class="sidebar-header">
      <a href="/" class="back-button" aria-label="Back to home">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        <span>Back</span>
      </a>
    </div>
    <h2>Documentation</h2>
    {#each docs as doc}
      <a href={`/docs/${doc.slug}`}>{doc.title}</a>
    {/each}
  </aside>

  <main class="content">
    <slot />
  </main>
</div>

<style>
.docs-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100vh;
  background: #0f172a;
  color: #e5e7eb;
}
.sidebar {
  background: #020617;
  padding: 16px;
  border-right: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
}
.sidebar-header {
  margin-bottom: 20px;
}
.back-button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  color: #94a3b8;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
  font-size: 14px;
}
.back-button:hover {
  background: #1e293b;
  color: #e5e7eb;
}
.sidebar h2 {
  margin-bottom: 12px;
  font-size: 18px;
  color: #e5e7eb;
}
.sidebar a:not(.back-button) {
  display: block;
  padding: 8px 12px;
  color: #cbd5f5;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
  margin-bottom: 4px;
}
.sidebar a:not(.back-button):hover {
  background: #1e293b;
  color: #fff;
}
.content {
  padding: 32px;
  overflow-y: auto;
}
</style>
