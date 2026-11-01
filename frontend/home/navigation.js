const routePattern =
  /^(enroll|request|visits|payout|availability|team|helping|help|callback|visit\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/;

export function homeSiteLinks(environment = {}) {
  const publicOverview = environment.PROD === true && environment.VITE_HOME_PRIVATE_ACCEPTANCE !== "1";
  return {
    publicOverview,
    overview: publicOverview ? "https://cookcredit.com/home/" : "#home",
    how: publicOverview ? "https://cookcredit.com/home/#how" : "#how",
    cookcredit: "https://cookcredit.com/",
  };
}

export function legacyHomeDestination(hash, environment = {}) {
  const links = homeSiteLinks(environment);
  if (!links.publicOverview || typeof hash !== "string") return null;
  const page = hash.replace(/^#/, "").split("?")[0];
  // Only fixed overview destinations cross origins. Account codes, visit IDs
  // and return parameters stay in the private portal and are never forwarded.
  if (page === "" || page === "home") return links.overview;
  if (page === "how") return links.how;
  if (page === "main") return links.overview + "#main";
  return null;
}

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
