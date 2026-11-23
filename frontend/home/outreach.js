// Fixed destinations prevent drafts from turning into misleading payment or
// sign-in links. Account verification and quote approvals retain their flow.
export const outreachPictures = {
  dinner: { file: "/assets/home-dinner.jpg", alt: "Illustrative roast chicken and vegetables" },
  stew: { file: "/assets/home-stew.jpg", alt: "Illustrative vegetable and white bean stew" },
};
export const outreachDestinations = {
  enroll: "Choose my service needs",
  help: "Ask us to call",
  visits: "Open my visits",
};
export const outreachTemplates = [
  { title: "A little help with dinner", subject: "Good food. A little help at home.", body: "A home-cooked meal. A kitchen left tidy. More time for you.\n\nTell CookCredit whether you need cooking, cleaning or both. We’ll discuss your needs and confirm availability before a visit.", design: { image: "dinner", destination: "enroll" } },
  { title: "Prefer a conversation?", subject: "Let’s talk about what would help.", body: "Looking for help with meals or cleaning at home? You don’t have to figure it all out online.\n\nAsk CookCredit to call you. We’ll discuss what you need and explain the next steps. No payment is needed to request a call.", design: { image: "stew", destination: "help" } },
  { title: "For returning customers", subject: "Your next visit starts here.", body: "Ready for a little help at home? Open your CookCredit account to review your visits or request another.\n\nYou’ll review your helper, visit details and full quote before paying. Availability is confirmed for each visit.", design: { image: "dinner", destination: "visits" } },
];
export function outreachLink(base, destination) {
  const url = new URL(base);
  if (!Object.hasOwn(outreachDestinations, destination)) throw new Error("Choose a CookCredit destination.");
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/" ||
      !(url.protocol === "https:" || (url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname))))
    throw new Error("The CookCredit address could not be verified.");
  return url.origin + "/#" + destination;
}
export function outreachText(draft, base) {
  return `${draft.subject}\n\n${draft.body}\n\n${outreachDestinations[draft.design.destination]}: ${outreachLink(base, draft.design.destination)}\n\nCookCredit · Enrollment is free. Review your full quote before paying for a visit.`;
}
export function emailDraftLink(subject, plain) {
  return "mailto:?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(plain);
}
