import test from 'node:test';
import assert from 'node:assert/strict';
import {readServiceAddress, formatServiceAddress} from '../home/serviceAddress.js';

test('postal form preserves the unit, normalizes fields and formats the server contract', () => {
  const form = new FormData();
  for (const [key,value] of Object.entries({street:' 100 Example Street ',unit:' Unit 2 ',city:' Atlanta ',state:'ga',postalCode:'30315'})) form.set(key,value);
  const result = readServiceAddress(form);
  assert.deepEqual(result,{street:'100 Example Street',unit:'Unit 2',city:'Atlanta',state:'GA',postalCode:'30315',country:'US'});
  assert.equal(formatServiceAddress(result),'100 Example Street, Unit 2, Atlanta, GA 30315');
  assert.equal(formatServiceAddress({...result,unit:''}),'100 Example Street, Atlanta, GA 30315');
});
