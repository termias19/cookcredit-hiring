import test from 'node:test'
import assert from 'node:assert/strict'
import {visitSchedule, visitStatusLabel, instructionLabel, preferences, cleaningTasks} from '../home/visitPresentation.js'

test('visit schedule preserves service wall time across device zones and daylight saving changes',()=>{
  const old=process.env.TZ
  try {
    for(const zone of ['UTC','America/Los_Angeles','Asia/Tokyo']) {
      process.env.TZ=zone
      assert.deepEqual(visitSchedule('2026-11-07','10:00:00','America/New_York'),{
        date:'Saturday, November 7, 2026',time:'10:00 AM',zone:'Eastern time'})
      assert.equal(visitSchedule('2026-03-08','00:30','America/New_York').time,'12:30 AM')
      assert.equal(visitSchedule('2026-11-01','13:30','America/New_York').time,'1:30 PM')
    }
  } finally { if(old===undefined)delete process.env.TZ;else process.env.TZ=old }
})

test('incomplete schedule displays an explicit pending value rather than Invalid Date or a false time',()=>{
  assert.deepEqual(visitSchedule(null,'25:99',null),{
    date:'Date to be reviewed',time:'Time to be reviewed',zone:'Service time zone'})
})

test('saved instruction names match every request choice without changing stored identifiers',()=>{
  for(const [value,title] of [...preferences,...cleaningTasks])assert.equal(instructionLabel(value),title)
  assert.equal(instructionLabel('future_preference'),'future preference')
  assert.equal(visitStatusLabel('requested'),'Request received')
  assert.equal(visitStatusLabel('confirmed'),'Visit confirmed')
})
