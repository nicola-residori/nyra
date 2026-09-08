const memoryStatus = document.querySelector('#memory-status');
function memoryKey(prefix) { return `${prefix}-${crypto.randomUUID()}`; }
async function memoryRequest(method, path, payload) {
  const response = await fetch(path, {method, headers: {'Content-Type':'application/json'}, body: payload ? JSON.stringify(payload) : undefined});
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json();
}
function owner(scope, form) { const value = form.elements.owner_user_id.value.trim(); return scope === 'USER' ? value : null; }
function report(error) { if (memoryStatus) { memoryStatus.textContent = error ? `Errore: ${error.message}` : 'Operazione completata.'; memoryStatus.className = error ? 'detail-error' : 'success card'; } }

document.querySelector('#operational-form')?.addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const scope = form.elements.scope.value;
  try {
    await memoryRequest('POST', '/admin-api/memory/operational', {
      entry_type: form.elements.entry_type.value, scope, owner_user_id: owner(scope, form),
      key: form.elements.key.value.trim(), value: JSON.parse(form.elements.value.value),
      enabled: form.elements.enabled.checked, idempotency_key: memoryKey('operational')
    }); location.reload();
  } catch (error) { report(error); }
});

document.querySelector('#semantic-form')?.addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const scope = form.elements.scope.value;
  try {
    await memoryRequest('POST', '/admin-api/memory/semantic', {
      memory_type: form.elements.memory_type.value, scope, owner_user_id: owner(scope, form),
      content: form.elements.content.value.trim(), source: form.elements.source.value,
      idempotency_key: memoryKey('semantic')
    }); location.reload();
  } catch (error) { report(error); }
});

document.querySelectorAll('[data-delete-entry]').forEach((button) => button.addEventListener('click', async () => {
  const id = button.dataset.deleteEntry;
  if (confirm(`Eliminare esattamente la regola ${id}?`)) { try { await memoryRequest('DELETE', `/admin-api/memory/operational/${encodeURIComponent(id)}`, {idempotency_key: memoryKey('delete')}); location.reload(); } catch (error) { report(error); } }
}));
document.querySelectorAll('[data-confirm-memory]').forEach((button) => button.addEventListener('click', async () => {
  const id = button.dataset.confirmMemory; try { await memoryRequest('POST', `/admin-api/memory/semantic/${encodeURIComponent(id)}/confirm`, {idempotency_key: memoryKey('confirm')}); location.reload(); } catch (error) { report(error); }
}));
document.querySelectorAll('[data-replace-memory]').forEach((button) => button.addEventListener('click', async () => {
  const supersedes_memory_id = button.dataset.replaceMemory;
  const content = prompt('Nuovo contenuto', button.dataset.content || ''); if (!content) return;
  const card = button.closest('[data-memory-id]'); const meta = card.querySelector('.eyebrow').textContent.split('·').map((value) => value.trim());
  const userId = card.dataset.ownerId || null;
  try { await memoryRequest('POST', '/admin-api/memory/semantic', {memory_type: meta[0], scope: meta[1], owner_user_id: meta[1] === 'USER' ? userId : null, content, source: 'USER_EXPLICIT', idempotency_key: memoryKey('replace'), supersedes_memory_id}); location.reload(); } catch (error) { report(error); }
}));
document.querySelectorAll('[data-delete-memory]').forEach((button) => button.addEventListener('click', async () => {
  const id = button.dataset.deleteMemory;
  if (confirm(`Eliminare definitivamente il ricordo ${id}?`)) { try { await memoryRequest('DELETE', `/admin-api/memory/semantic/${encodeURIComponent(id)}`, {idempotency_key: memoryKey('delete')}); location.reload(); } catch (error) { report(error); } }
}));
