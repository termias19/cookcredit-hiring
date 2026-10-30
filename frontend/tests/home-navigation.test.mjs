import test from "node:test";
import assert from "node:assert/strict";
import { safeHomeRoute } from "../home/navigation.js";
import { homeScreenCategory } from "../src/utils/errorReporting.js";
test("Home email continuation accepts only internal task routes", () => {
  for (const route of [
    "request",
    "helping",
    "payout",
    "visit/11111111-1111-4111-8111-111111111111",
  ])
    assert.equal(safeHomeRoute(route), route);
  for (const route of [
    "https://evil.example",
    "//evil.example",
    "javascript:alert(1)",
    "visit/../../team",
    "team?next=https://evil.example",
    null,
    {},
    "account/action?oobCode=private",
  ])
    assert.equal(safeHomeRoute(route), "visits");
});
test("Home diagnostics categorize routes without sending private identifiers or codes", () => {
  assert.equal(
    homeScreenCategory("#visit/11111111-1111-4111-8111-111111111111"),
    "home_customer",
  );
  assert.equal(homeScreenCategory("#account/action?oobCode=private"), "auth");
  assert.equal(homeScreenCategory("#team"), "home_operator");
  assert.equal(homeScreenCategory("#payout"), "home_helper");
});
