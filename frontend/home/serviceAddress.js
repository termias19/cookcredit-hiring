// User-entered postal data. Never infer a location or call a map provider.
export function formatServiceAddress(value) {
  return [value.street, value.unit, `${value.city}, ${value.state} ${value.postalCode}`]
    .filter(Boolean).join(", ");
}

export const repeatLabels = {
  once: "Just this visit",
  weekly: "Every week",
  fortnightly: "Every 2 weeks",
  every_four_weeks: "Every 4 weeks",
};

export function readServiceAddress(form) {
  const value = Object.fromEntries(["street", "unit", "city", "state", "postalCode"].map(key =>
    [key, String(form.get(key) || "").trim()]));
  return { ...value, state: value.state.toUpperCase(), country: "US" };
}
