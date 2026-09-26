"""Staging-only receiver: verify HMAC, fail the first delivery, deduplicate retries."""
import hashlib
import hmac
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import redis

assert os.environ['COOKCREDIT_ENVIRONMENT'] == 'staging'
secret = os.environ['PROBE_WEBHOOK_SECRET']
cache = redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/health':
            return self.respond(200 if cache.ping() else 503, {'receiver': 'staging'})
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+secret):
            return self.respond(401, {})
        event_id = self.path.removeprefix('/probe/')
        if not re.fullmatch('[a-f0-9-]{36}', event_id):
            return self.respond(400, {})
        self.respond(200, cache.hgetall('cc:staging:hookprobe:'+event_id))

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        if self.path != '/event' or not 0 < size <= 65536:
            return self.respond(400, {})
        body = self.rfile.read(size)
        try:
            signature = dict(piece.split('=', 1) for piece in self.headers.get('CookCredit-Signature', '').split(','))
            timestamp = int(signature['t'])
            expected = hmac.new(secret.encode(), str(timestamp).encode()+b'.'+body, hashlib.sha256).hexdigest()
            valid = abs(time.time()-timestamp) <= 300 and hmac.compare_digest(expected, signature['v1'])
            payload = json.loads(body)
            event_id = payload['id']
            valid = valid and event_id == self.headers.get('CookCredit-Event-Id') and payload.get('environment') == 'test'
            valid = valid and bool(re.fullmatch('[a-f0-9-]{36}', event_id))
        except (ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            return self.respond(401, {})
        key = 'cc:staging:hookprobe:'+event_id
        count = cache.hincrby(key, 'attempts', 1)
        cache.expire(key, 86400)
        if count == 1:
            return self.respond(503, {'syntheticFailure': True})
        first = cache.hsetnx(key, 'accepted', '1')
        self.respond(200, {'accepted': True, 'duplicate': not first})


ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
