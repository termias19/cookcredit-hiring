const routePattern =
  /^(enroll|request|visits|payout|availability|team|helping|help|callback|visit\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/;
export const safeHomeRoute = (value, enrollmentOnly = false) => {
  const fallback = enrollmentOnly ? "enroll" : "visits";
  if (typeof value !== "string" || !routePattern.test(value)) return fallback;
  return enrollmentOnly && !["enroll", "help", "callback", "team"].includes(value) ? fallback : value;
};
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
