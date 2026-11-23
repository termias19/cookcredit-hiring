// Preparation must obey the same deadline as fetch. A late security token
// must never start a mutation after the caller has already timed out.
export async function waitForRequest(prepare, signal) {
  const expired = () => new DOMException("Request deadline expired", "AbortError");
  if (signal.aborted) throw expired();
  let abort;
  const cancelled = new Promise((_, reject) => {
    abort = () => reject(expired());
    signal.addEventListener("abort", abort, { once: true });
  });
  try {
    const value = await Promise.race([
      Promise.resolve().then(() => {
        if (signal.aborted) throw expired();
        return prepare();
      }),
      cancelled,
    ]);
    if (signal.aborted) throw expired();
    return value;
  } finally {
    signal.removeEventListener("abort", abort);
  }
}
