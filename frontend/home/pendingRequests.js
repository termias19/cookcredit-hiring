// Persist only opaque references for unacknowledged mutations. Never put an
// address, instruction, identity, token, file or request body into Web Storage.
export function createPendingRequests({ storage = () => globalThis.sessionStorage,
  cryptoProvider = globalThis.crypto, now = () => Date.now() } = {}) {
  const name = "cookcredit.home.pending.v1", pending = new Map(), completed = new Map();
  try {
    const entries = JSON.parse(storage()?.getItem(name) || "[]");
    if (Array.isArray(entries)) for (const entry of entries.slice(0, 60)) {
      if (Array.isArray(entry) && /^[a-f0-9]{64}$/.test(entry[0]) && /^[a-f0-9-]{36}$/.test(entry[1])) pending.set(...entry);
    }
  } catch { /* Restricted storage keeps same-page retries in memory. */ }
  const persist = () => {
    try { const target = storage(); if (!target) return false; target.setItem(name, JSON.stringify([...pending])); return true; }
    catch { return false; }
  };
  const digest = async value => {
    if (!cryptoProvider?.subtle) throw new Error("Open CookCredit in an up-to-date browser to send this request safely.");
    const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
    return Array.from(new Uint8Array(await cryptoProvider.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  };
  return {
    async reserve({ uid, method, path, body, form, signal, startedAt = now() }) {
      let content = body;
      if (form) {
        const file = body.get("file");
        if (!file?.arrayBuffer || !file.size || file.size > 8 * 1024 * 1024) throw new Error("Choose a receipt photo up to 8 MB.");
        content = { fileSha256: await digest(await file.arrayBuffer()) };
      }
      const fingerprint = await digest(JSON.stringify([uid || "anonymous", method, path, content]));
      if (signal?.aborted) throw new DOMException("Request deadline expired", "AbortError");
      const prior = completed.get(fingerprint);
      // A concurrent call that began before another copy was acknowledged must
      // still reuse that reference, even if its token/file hashing finished late.
      if (prior && startedAt <= prior.at) return { fingerprint, key: prior.key, durable: true };
      if (!pending.has(fingerprint)) {
        if (pending.size >= 60) throw new Error("Too many unfinished requests. Retry an existing request or contact CookCredit before starting another.");
        pending.set(fingerprint, cryptoProvider.randomUUID());
      }
      return { fingerprint, key: pending.get(fingerprint), durable: persist() };
    },
    acknowledge(reference) {
      if (!reference) return;
      if (pending.get(reference.fingerprint) === reference.key) pending.delete(reference.fingerprint);
      completed.set(reference.fingerprint, { key: reference.key, at: now() });
      if (completed.size > 60) completed.delete(completed.keys().next().value);
      persist();
    },
  };
}
