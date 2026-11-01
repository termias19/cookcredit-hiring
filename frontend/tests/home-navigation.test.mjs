import test from "node:test";
import assert from "node:assert/strict";
import { safeHomeRoute, homeSiteLinks, legacyHomeDestination } from "../home/navigation.js";
import { homeScreenCategory } from "../src/utils/errorReporting.js";
test("Home email continuation accepts only internal task routes", () => {
  for (const route of [
    "request",
    "enroll",
    "helping",
    "payout",
    "availability",
    "help",
    "callback",
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
  assert.equal(homeScreenCategory("#enroll"), "home_customer");
  assert.equal(homeScreenCategory("#payout"), "home_helper");
  assert.equal(homeScreenCategory("#availability"), "home_helper");
});

test('public enrollment account returns never reopen booking or helper routes',()=>{
  for(const route of ['request','visits','payout','availability','helping','visit/11111111-1111-4111-8111-111111111111','https://evil.example',null])
    assert.equal(safeHomeRoute(route,true),'enroll')
  for(const route of ['enroll','help','callback','team'])assert.equal(safeHomeRoute(route,true),route)
  assert.equal(safeHomeRoute('request',false),'request')
})

test('only production overview aliases leave the portal, with no private parameters forwarded',()=>{
  const environment={PROD:true};const links=homeSiteLinks(environment)
  assert.equal(links.overview,'https://cookcredit.com/home/')
  assert.equal(links.how,'https://cookcredit.com/home/#how')
  for(const route of ['', '#home','#home?next=https://unrelated.example'])
    assert.equal(legacyHomeDestination(route,environment),links.overview)
  assert.equal(legacyHomeDestination('#how?source=old-link',environment),links.how)
  assert.equal(legacyHomeDestination('#main',environment),links.overview+'#main')
  for(const route of ['#help','#callback','#enroll','#request','#team','#payout','#availability',
    '#sign-in?next=team','#account/action?oobCode=private','#visit/11111111-1111-4111-8111-111111111111',
    '#https://unrelated.example',null,{}])assert.equal(legacyHomeDestination(route,environment),null)
  for(const env of [{},{PROD:false},{PROD:true,VITE_HOME_PRIVATE_ACCEPTANCE:'1'}]){
    assert.equal(homeSiteLinks(env).overview,'#home')
    assert.equal(legacyHomeDestination('#home',env),null)
    assert.equal(legacyHomeDestination('#how',env),null)
  }
})
