class NyraEnrollmentPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._sessions = []; this._wakeSessions = []; this._sources = [];
    this._busy = false; this._wakeBusy = false; this._error = ""; this._wakeError = ""; this._wakeSampleCount = null;
  }
  set hass(value) { this._hass = value; if (!this._initialized) { this._initialized = true; this._load(); } }
  set panel(value) { this._panel = value; }
  async _load() {
    try {
      const [enrollment, wakeWord] = await Promise.all([
        this._hass.callWS({ type: "nyra/enrollment/state" }),
        this._hass.callWS({ type: "nyra/wake-word/state" }),
      ]);
      this._sources = [...new Set([...(enrollment.sources || []), ...(wakeWord.sources || [])])];
      this._sessions = enrollment.sessions || []; this._wakeSessions = wakeWord.sessions || [];
      this._unsubscribeEnrollment = await this._hass.connection.subscribeEvents(
        (event) => this._applyEnrollmentUpdate(event.data), "nyra_enrollment_updated");
      this._unsubscribeWakeWord = await this._hass.connection.subscribeEvents(
        (event) => this._applyWakeWordUpdate(event.data), "nyra_wake_word_capture_updated");
      await this._loadWakeCount((this._wakeSession && this._wakeSession.wake_word_text) || "Nyra");
    } catch (error) { this._error = this._message(error); }
    this._render();
  }
  disconnectedCallback() {
    if (this._unsubscribeEnrollment) this._unsubscribeEnrollment();
    if (this._unsubscribeWakeWord) this._unsubscribeWakeWord();
  }
  _applyEnrollmentUpdate(session) {
    const index = this._sessions.findIndex((item) => item.session_id === session.session_id);
    if (index === -1) this._sessions.push(session); else this._sessions[index] = session;
    this._busy = false; this._render();
  }
  _applyWakeWordUpdate(session) {
    const index = this._wakeSessions.findIndex((item) => item.session_id === session.session_id);
    if (index === -1) this._wakeSessions.push(session); else this._wakeSessions[index] = session;
    this._wakeBusy = false; this._render();
  }
  async _loadWakeCount(wakeWordText) {
    if (!wakeWordText.trim()) return;
    try {
      const result = await this._hass.callWS({ type: "nyra/wake-word/sample-count", wake_word_text: wakeWordText.trim() });
      this._wakeSampleCount = result.sample_count;
    } catch (_) { this._wakeSampleCount = null; }
  }
  get _session() { return [...this._sessions].reverse().find((item) => ["ACTIVE", "COMPLETED", "TERMINATED"].includes(item.status)); }
  get _wakeSession() { return [...this._wakeSessions].reverse()[0]; }
  async _call(message) {
    this._busy = true; this._error = ""; this._render();
    try { this._applyEnrollmentUpdate(await this._hass.callWS(message)); }
    catch (error) { this._busy = false; this._error = this._message(error); this._render(); }
  }
  async _captureWakeWord() {
    const source = this.shadowRoot.querySelector("#wake-source").value;
    const wakeWordText = this.shadowRoot.querySelector("#wake-word-text").value.trim();
    if (!wakeWordText) { this._wakeError = "Inserisci la wake word da registrare."; this._render(); return; }
    this._wakeBusy = true; this._wakeError = ""; this._render();
    try {
      const result = await this._hass.callWS({ type: "nyra/wake-word/capture", source_id: source, language: "it-IT", wake_word_text: wakeWordText });
      this._applyWakeWordUpdate(result);
    } catch (error) { this._wakeBusy = false; this._wakeError = this._message(error); this._render(); }
  }
  _message(error) {
    const code = error && error.code;
    if (code === "unauthorized") return "Accedi a Home Assistant per usare la configurazione vocale.";
    if (code === "enrollment_conflict") return "Lo speaker è già impegnato in una registrazione.";
    return (error && error.message) || "La registrazione non è riuscita. Riprova.";
  }
  _escape(value) { return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character]); }
  _start() { this._call({ type: "nyra/enrollment/start", source_id: this.shadowRoot.querySelector("#source").value, language: "it-IT", sample_count: Number(this.shadowRoot.querySelector("#count").value || 6) }); }
  _record() { this._call({ type: "nyra/enrollment/record", session_id: this._session.session_id }); }
  _terminate() { this._call({ type: "nyra/enrollment/terminate", session_id: this._session.session_id }); }
  _sourceOptions() { return this._sources.map((source) => `<option value="${this._escape(source)}">${this._escape(source)}</option>`).join(""); }
  _render() {
    const session = this._session; const active = session && session.status === "ACTIVE";
    const capture = session && session.capture_state; const locked = this._busy || capture === "RECORDING" || capture === "PROCESSING";
    const phrase = session && session.current_phrase && session.current_phrase.text;
    const resultClass = ["ACCEPTED", "COMPLETED"].includes(capture) ? "good" : ["REJECTED", "FAILED"].includes(capture) ? "bad" : "";
    const resultText = { READY: "Pronto per il prossimo campione", RECORDING: "In ascolto… parla e poi resta in silenzio", PROCESSING: "Invio e verifica del campione…", ACCEPTED: "Campione accettato", REJECTED: "Campione non valido: ripeti la stessa frase", FAILED: "Verifica non riuscita: riprova", COMPLETED: "Profilo vocale completato", TERMINATED: "Registrazione interrotta" }[capture] || "";
    const wake = this._wakeSession; const wakeState = wake && wake.capture_state;
    const wakeClass = wakeState === "ACCEPTED" ? "good" : ["REJECTED", "FAILED"].includes(wakeState) ? "bad" : "";
    const wakeText = { RECORDING: "In ascolto… pronuncia la wake word e poi resta in silenzio", ACCEPTED: "Campione salvato", REJECTED: "Campione non valido: riprova", FAILED: "Registrazione non riuscita: riprova" }[wakeState] || "";
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;padding:24px;color:var(--primary-text-color)}.page{max-width:820px;margin:0 auto}h1{margin:0 0 8px;font-size:30px}.lead,.intro{color:var(--secondary-text-color)}.lead{margin:0 0 24px}ha-card{display:block;padding:26px;border-radius:22px;margin-bottom:20px}h2{margin:0 0 6px;font-size:23px}.intro{margin:0 0 20px;line-height:1.45}.setup{display:grid;grid-template-columns:1fr 150px;gap:14px}.wake-setup{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:flex;flex-direction:column;gap:7px;font-size:13px;color:var(--secondary-text-color)}select,input{padding:12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:var(--primary-text-color);font-size:16px}.phrase{margin:22px 0;padding:22px;border-radius:16px;background:color-mix(in srgb,var(--primary-color) 10%,transparent);text-align:center;font-size:24px;line-height:1.35}.progress{display:flex;justify-content:space-between;align-items:center;font-weight:600}progress{width:100%;height:10px;margin:10px 0 18px;accent-color:var(--primary-color)}.result{min-height:24px;text-align:center;font-weight:600;margin:12px 0}.good{color:var(--success-color,#2e7d32)}.bad{color:var(--error-color,#c62828)}.actions{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}button{border:0;border-radius:999px;padding:13px 22px;cursor:pointer;font-weight:700;font-size:15px}button.primary{color:var(--text-primary-color,white);background:var(--primary-color)}button.secondary{color:var(--primary-text-color);background:var(--secondary-background-color)}button:disabled{opacity:.45;cursor:default}.error{margin-top:18px;padding:12px;border-radius:10px;color:var(--error-color);background:color-mix(in srgb,var(--error-color) 10%,transparent)}@media(max-width:600px){:host{padding:12px}ha-card{padding:20px}.setup,.wake-setup{grid-template-columns:1fr}.phrase{font-size:21px}}
      </style>
      <div class="page"><h1>Configurazione Nyra</h1><p class="lead">Configura il riconoscimento delle persone e raccogli i campioni per le wake word.</p>
      <ha-card><h2>Profilo vocale</h2><p class="intro">Crea o aggiorna il profilo usato per riconoscere chi sta parlando.</p>
      ${!active ? `${session && session.status === "COMPLETED" ? `<div class="result good">Profilo vocale completato</div>` : ""}<div class="setup"><label>Speaker<select id="source">${this._sourceOptions()}</select></label><label>Campioni<input id="count" type="number" min="1" max="24" value="6"></label></div><div class="actions" style="margin-top:22px"><button id="start" class="primary" ${this._busy || !this._sources.length ? "disabled" : ""}>Crea o aggiorna profilo</button></div>` : `<div class="progress"><span>${this._escape(session.source_id)}</span><span>${session.accepted_count} / ${session.target_count}</span></div><progress max="${session.target_count}" value="${session.accepted_count}"></progress><div class="phrase">${this._escape(phrase || "Completamento in corso…")}</div><div class="result ${resultClass}">${resultText}</div><div class="actions"><button id="record" class="primary" ${locked ? "disabled" : ""}>Registra campione</button><button id="terminate" class="secondary" ${locked ? "disabled" : ""}>Interrompi</button></div>`}
      ${this._error ? `<div class="error">${this._escape(this._error)}</div>` : ""}</ha-card>
      <ha-card><h2>Campioni wake word</h2><p class="intro">Registra un campione alla volta. Varia distanza, posizione, tono, volume, rumore ambientale e contesto quotidiano. I campioni salvati saranno gestibili in Nyra Admin.</p><div class="wake-setup"><label>Wake word<input id="wake-word-text" maxlength="120" value="${this._escape((wake && wake.wake_word_text) || "Nyra")}"></label><label>Speaker<select id="wake-source">${this._sourceOptions()}</select></label></div><div class="result">Campioni già salvati: ${this._wakeSampleCount === null ? "—" : this._wakeSampleCount}</div><div class="result ${wakeClass}">${wakeText}</div><div class="actions"><button id="capture-wake-word" class="primary" ${this._wakeBusy || !this._sources.length || wakeState === "RECORDING" ? "disabled" : ""}>Registra un campione</button></div>${this._wakeError ? `<div class="error">${this._escape(this._wakeError)}</div>` : ""}</ha-card></div>`;
    this.shadowRoot.querySelector("#start")?.addEventListener("click", () => this._start());
    this.shadowRoot.querySelector("#record")?.addEventListener("click", () => this._record());
    this.shadowRoot.querySelector("#terminate")?.addEventListener("click", () => this._terminate());
    this.shadowRoot.querySelector("#capture-wake-word")?.addEventListener("click", () => this._captureWakeWord());
    this.shadowRoot.querySelector("#wake-word-text")?.addEventListener("change", async (event) => { await this._loadWakeCount(event.target.value); this._render(); });
  }
}
if (!customElements.get("nyra-enrollment-panel")) customElements.define("nyra-enrollment-panel", NyraEnrollmentPanel);
