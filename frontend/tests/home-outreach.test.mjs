import test from "node:test";
import assert from "node:assert/strict";
import { outreachLink, outreachText, emailDraftLink, outreachTemplates } from "../home/outreach.js";

test("outreach destinations preserve account/quote routes without a payment bypass", () => {
  assert.equal(outreachLink("https://cookcredit-home.web.app/", "enroll"), "https://cookcredit-home.web.app/#enroll");
  assert.equal(outreachLink("http://127.0.0.1:53409/", "help"), "http://127.0.0.1:53409/#help");
  assert.equal(outreachLink("https://cookcredit-home.web.app/", "visits"), "https://cookcredit-home.web.app/#visits");
  for (const bad of ["checkout", "javascript:alert(1)", "//elsewhere.example", "visits?next=evil", "__proto__"])
    assert.throws(() => outreachLink("https://cookcredit-home.web.app/", bad));
  for (const bad of ["javascript:alert(1)", "https://user:pass@elsewhere.example/", "https://cookcredit-home.web.app/?token=private", "http://elsewhere.example/"])
    assert.throws(() => outreachLink(bad,"enroll"));
});

test("manual email drafts cannot inject recipients/headers; links work as plain text", () => {
  const draft = {...outreachTemplates[0], subject: "Dinner & more?\nBcc: other@example.test"};
  const text = outreachText(draft, "https://cookcredit-home.web.app/");
  assert.ok(text.includes("https://cookcredit-home.web.app/#enroll"));
  assert.ok(text.includes("Review your full quote before paying"));
  const link = emailDraftLink(draft.subject,text);
  assert.equal(new URL(link).pathname, "");
  assert.ok(!link.includes("\n"));
  assert.ok(!link.includes("&bcc="));
  assert.equal(new URL(link).searchParams.get("body"),text);
});
