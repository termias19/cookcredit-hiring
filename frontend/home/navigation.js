const routePattern =
  /^(enroll|request|visits|payout|team|helping|visit\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/;
export const safeHomeRoute = (value) =>
  typeof value === "string" && routePattern.test(value) ? value : "visits";
export function readReturnRoute() {
  try {
    return sessionStorage.getItem("homeReturn");
  } catch {
    return null;
  }
}
export function rememberReturnRoute(value) {
  try {
    sessionStorage.setItem("homeReturn", safeHomeRoute(value));
  } catch {
    /* Links also carry the safe route. */
  }
}
export function forgetReturnRoute() {
  try {
    sessionStorage.removeItem("homeReturn");
  } catch {
    /* Storage is optional. */
  }
}
