function selected(selector) { return [...document.querySelectorAll(selector + ':checked')].map((item) => item.value); }
async function jsonRequest(method, path, body) {
  const response = await fetch(path, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(await response.text());
  return response;
}
document.querySelectorAll('[data-delete-profile-samples]').forEach((button) => button.addEventListener('click', async () => {
  const user = button.dataset.deleteProfileSamples;
  const ids = selected(`.profile-sample[data-user="${CSS.escape(user)}"]`);
  if (ids.length && confirm(`Eliminare ${ids.length} campioni?`)) { await jsonRequest('DELETE', `/admin-api/speaker-identity/profiles/${encodeURIComponent(user)}/samples`, {sample_ids: ids}); location.reload(); }
}));
document.querySelectorAll('[data-select-profile]').forEach((toggle) => toggle.addEventListener('change', () => document.querySelectorAll(`.profile-sample[data-user="${CSS.escape(toggle.dataset.selectProfile)}"]`).forEach((item) => { item.checked = toggle.checked; })));
document.querySelectorAll('[data-delete-profile-sample]').forEach((button) => button.addEventListener('click', async () => {
  if (confirm('Eliminare questo campione?')) { await jsonRequest('DELETE', `/admin-api/speaker-identity/profiles/${encodeURIComponent(button.dataset.user)}/samples`, {sample_ids: [button.dataset.deleteProfileSample]}); location.reload(); }
}));
document.querySelectorAll('[data-delete-profile]').forEach((button) => button.addEventListener('click', async () => {
  const user = button.dataset.deleteProfile;
  if (confirm(`Eliminare l'intero profilo ${user}?`)) { await jsonRequest('DELETE', `/admin-api/speaker-identity/profiles/${encodeURIComponent(user)}`, {}); location.reload(); }
}));
document.querySelector('#select-all-wake')?.addEventListener('change', (event) => document.querySelectorAll('.wake-sample').forEach((item) => { item.checked = event.target.checked; }));
document.querySelector('#delete-wake')?.addEventListener('click', async () => {
  const ids = selected('.wake-sample'); if (ids.length && confirm(`Eliminare ${ids.length} campioni?`)) { await jsonRequest('DELETE', '/admin-api/speaker-identity/wake-words/samples', {sample_ids: ids}); location.reload(); }
});
document.querySelectorAll('[data-delete-wake-sample]').forEach((button) => button.addEventListener('click', async () => {
  if (confirm('Eliminare questo campione?')) { await jsonRequest('DELETE', '/admin-api/speaker-identity/wake-words/samples', {sample_ids: [button.dataset.deleteWakeSample]}); location.reload(); }
}));
document.querySelector('#export-wake')?.addEventListener('click', async () => {
  const ids = selected('.wake-sample'); if (!ids.length) return;
  const response = await jsonRequest('POST', '/admin-api/speaker-identity/wake-words/export', {sample_ids: ids});
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a'); link.href = url; link.download = 'wake-word-samples.tar.gz'; link.click(); URL.revokeObjectURL(url);
});
