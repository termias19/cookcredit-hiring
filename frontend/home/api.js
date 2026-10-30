import { auth, getAppCheckHeaders } from "../src/firebase";

const pending = new Map();
export async function api(
  path,
  { method = "GET", body, protectedAccount = false, form = false } = {},
) {
  const headers = {};
  if (auth.currentUser)
    headers.Authorization = "Bearer " + (await auth.currentUser.getIdToken());
  if (protectedAccount) Object.assign(headers, await getAppCheckHeaders());
  const fingerprint =
    method +
    ":" +
    path +
    ":" +
    (form
      ? body.get("file")?.name + ":" + body.get("file")?.size
      : JSON.stringify(body));
  if (method !== "GET") {
    if (!pending.has(fingerprint))
      pending.set(fingerprint, crypto.randomUUID());
    headers["Idempotency-Key"] = pending.get(fingerprint);
  }
  if (body !== undefined && !form) headers["Content-Type"] = "application/json";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), form ? 30000 : 15000);
  try {
    const response = await fetch("/api/home" + path, {
      method,
      headers,
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
    });
    const value = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(
        value.error || "We could not finish. Please retry.",
      );
      error.code = value.code;
      error.status = response.status;
      error.reference = value.reference || response.headers.get("X-Request-ID");
      throw error;
    }
    pending.delete(fingerprint);
    return value;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "This is taking longer than expected. Retry to check the same request safely.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export async function downloadReceipt(visit, id) {
  const response = await fetch(`/api/home/visits/${visit}/receipts/${id}`, {
    headers: {
      Authorization: "Bearer " + (await auth.currentUser.getIdToken()),
    },
    cache: "no-store",
    credentials: "omit",
  });
  if (!response.ok)
    throw new Error("The receipt could not be downloaded. Refresh and retry.");
  const blob = await response.blob(),
    url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `cookcredit-receipt-${id}.jpg`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export function stripeLocation(value) {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    ![
      "checkout.stripe.com",
      "connect.stripe.com",
      "dashboard.stripe.com",
    ].includes(url.hostname) ||
    url.username ||
    url.password
  )
    throw new Error("The secure Stripe address could not be verified.");
  window.location.assign(url.href);
}
export const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    value / 100,
  );
export const label = (value) => String(value || "").replaceAll("_", " ");
export function dollars(value) {
  if (!/^\d+(\.\d{1,2})?$/.test(value))
    throw new Error(
      "Enter a dollar amount with no more than two decimal places.",
    );
  const [whole, fraction = ""] = value.split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(cents)) throw new Error("The amount is too large.");
  return cents;
}
