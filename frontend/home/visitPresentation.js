// Shared labels keep the request form and saved visit consistent. Stored values
// remain unchanged; these are presentation labels, not new booking categories.
export const serviceNames = { cooking: "Cooking", cleaning: "Cleaning", both: "Cooking and cleaning", not_sure: "Help choosing" };
export const preferences = [
  ["allergies", "Food allergies or ingredients to avoid"],
  ["provided_meal_instructions", "Follow meal instructions I already have"],
  ["easy_to_chew", "Easy-to-chew meals"],
  ["label_meals", "Label meals and dates"],
  ["storage_help", "Help putting meals away"],
  ["fragrance_free", "Avoid fragranced cleaning products"],
  ["customer_supplies", "Use my cleaning supplies"],
  ["phone_help", "Discuss my request by phone first"],
];
export const cleaningTasks = [
  ["kitchen", "Kitchen surfaces"],
  ["dishes", "Dishes"],
  ["bathroom", "Bathroom"],
  ["floors", "Floors"],
  ["laundry", "Laundry"],
  ["general_tidy", "General tidying"],
];
const instructionNames = Object.fromEntries([...preferences, ...cleaningTasks]);
export const instructionLabel = value => instructionNames[value] || String(value || "").replaceAll("_", " ");

export const visitStatusLabel = status => ({
  requested: "Request received", accepted: "Quote and payment review",
  confirmed: "Visit confirmed", in_progress: "Visit in progress",
  pending_confirmation: "Ready for your review", completed: "Visit completed",
  cancelled: "Visit cancelled",
})[status] || "Visit update";

export function visitSchedule(date, time, timeZone) {
  // These fields are a local calendar date and wall-clock time, not a UTC
  // timestamp. Format without shifting them to the viewer's device time zone.
  const day = /^\d{4}-\d{2}-\d{2}$/.test(date || "") ? new Date(`${date}T12:00:00Z`) : null;
  const parts = /^(\d{2}):(\d{2})(?::\d{2})?$/.exec(time || "");
  const hours = parts ? Number(parts[1]) : -1;
  const minutes = parts ? Number(parts[2]) : -1;
  return {
    date: day && Number.isFinite(day.getTime())
      ? new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }).format(day)
      : "Date to be reviewed",
    time: hours >= 0 && hours < 24 && minutes >= 0 && minutes < 60
      ? `${hours % 12 || 12}:${String(minutes).padStart(2, "0")} ${hours < 12 ? "AM" : "PM"}`
      : "Time to be reviewed",
    zone: ({ "America/New_York": "Eastern time", "America/Chicago": "Central time",
      "America/Denver": "Mountain time", "America/Los_Angeles": "Pacific time" })[timeZone] || timeZone || "Service time zone",
  };
}
