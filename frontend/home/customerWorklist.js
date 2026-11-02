export const followupNames = { new: "Needs follow-up", contacted: "Contacted", waiting: "Waiting for customer", done: "Follow-up done" };
export function mergePeople(current, incoming) {
  const rows = new Map(current.map(row => [row.id, row]));
  for (const row of incoming) rows.set(row.id, row);
  return [...rows.values()];
}
export function contactName(name, email) {
  return typeof name === "string" && name.trim() && name.trim().toLowerCase() !== String(email || "").trim().toLowerCase() ? name.trim() : "";
}
