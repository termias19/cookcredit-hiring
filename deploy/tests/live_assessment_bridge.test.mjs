import test from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const { parseHiringContext, submitHiringAssessment } = await import(pathToFileURL(path.join(process.argv[2], 'hiring-bridge.mjs')));
const id = '123e4567-e89b-42d3-a456-426614174000';
const api = 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app';
const destination = `https://cookcredit-hiring-staging.web.app/application-assessment-return/${id}`;
function launch(extra = {}) {
  const url = new URL('https://cookcredit-knife-demo.web.app/hiring/');
  url.search = new URLSearchParams({hiringSession: id, apiOrigin: api, returnUrl: destination, ...extra});
  return url;
}
test('the staging handoff retains the exact session and application destination', () => {
  assert.deepEqual(parseHiringContext(launch()), {sessionId: id, apiOrigin: api, returnUrl: destination, mode: 'test'});
});
test('rejects credential-bearing URLs and unrelated return paths', () => {
  for (const extra of [{apiOrigin: `${api}/?token=secret`}, {returnUrl: destination+'?token=secret'},
    {returnUrl: 'https://cookcredit-hiring-staging.web.app/business'}, {hiringSession: 'bad-id'},
    {apiOrigin: 'https://attacker.invalid'}]) assert.throws(() => parseHiringContext(launch(extra)));
});
test('only assessment id is sent, with App Check and a bounded abort signal', async () => {
  let request;
  await submitHiringAssessment({context: parseHiringContext(launch()), assessmentId: 'recording_1',
    idToken: 'synthetic-id-token', appCheckToken: 'synthetic-app-check',
    fetchImpl: async (url, options) => {
      request = {url, ...options};
      return {ok: true, json: async () => ({status: 'processing'})};
    }});
  assert.equal(request.headers['X-Firebase-AppCheck'], 'synthetic-app-check');
  assert.equal(request.headers.Authorization, 'Bearer synthetic-id-token');
  assert.ok(request.signal instanceof AbortSignal);
  assert.deepEqual(JSON.parse(request.body), {assessmentId: 'recording_1'});
  assert.equal(request.credentials, 'omit');
  assert.equal(request.cache, 'no-store');
  assert.equal(new URL(request.url).search, '');
});
test('an invalid successful response does not report a completed submission', async () => {
  await assert.rejects(submitHiringAssessment({context: parseHiringContext(launch()), assessmentId: 'recording_1',
    idToken: 'synthetic-id-token', appCheckToken: 'synthetic-app-check',
    fetchImpl: async () => ({ok: true, json: async () => ({status: 'started'})})}), /unexpected/);
});


test('capture claims accompany the same assessment without sending scores', async () => {
  let body;
  const captureMetadata = {version:1, recording:'camera-stream'};
  await submitHiringAssessment({context:parseHiringContext(launch()), assessmentId:'recording_1',
    idToken:'synthetic', captureMetadata,
    fetchImpl:async (url, options) => {
      body = JSON.parse(options.body);
      return {ok:true, json:async () => ({status:'processing'})};
    }});
  assert.deepEqual(body, {assessmentId:'recording_1', captureMetadata});
});
