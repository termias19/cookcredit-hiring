import test from "node:test";
import assert from "node:assert/strict";
import { mergePeople, contactName } from "../home/customerWorklist.js";

test("overlapping pages or refreshes keep one account row and its latest data", () => {
  const rows = mergePeople([{ id:"u:customer", name:"Old", status:"new" }, { id:"c:request", name:"Unlinked call" }],
    [{ id:"u:customer", name:"Confirmed Name", status:"waiting" }, { id:"u:second", name:"Another customer" }]);
  assert.equal(rows.length,3);
  assert.deepEqual(rows.map(row=>row.id),["u:customer","c:request","u:second"]);
  assert.equal(rows[0].name,"Confirmed Name");
  assert.equal(rows[0].status,"waiting");
});

test("an email fallback is not presented or autofilled as a person's name", () => {
  assert.equal(contactName(" CUSTOMER@example.test ","customer@example.test"),"");
  assert.equal(contactName(" Jordan Smith ","customer@example.test"),"Jordan Smith");
  assert.equal(contactName(null,"customer@example.test"),"");
});
