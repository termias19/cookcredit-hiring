"""Public contact relay. Fixed recipient; no user accounts or hiring decisions."""
import hashlib, html, json, os, re, uuid
from flask import Flask, jsonify, request
from redis import Redis
from mail_transport import send_google_smtp

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 24576
RECIPIENT = 'connectwithus@cookcredit.com'
ORIGINS = {'https://cookcredit.com', 'https://www.cookcredit.com'}

def storage():
    return Redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=3, socket_timeout=3)

def fields(data):
    if not isinstance(data, dict) or set(data) - {'name','email','message','website','requestId'}:
        raise ValueError('Please check the form fields.')
    values = {}
    for key, maximum in [('name',100),('email',254),('message',5000),('website',200),('requestId',36)]:
        value = data.get(key, '')
        if not isinstance(value,str) or len(value)>maximum or '\x00' in value:
            raise ValueError('Please check the form fields and message length.')
        values[key] = value.strip()
    if values['website']:
        raise ValueError('Unable to send this submission.')
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",values['email']):
        raise ValueError('Enter a valid email address.')
    if not values['message']:
        raise ValueError('Enter a message.')
    try: uuid.UUID(values['requestId'])
    except (ValueError,AttributeError): raise ValueError('Refresh this page and try again.')
    return values

@app.after_request
def headers(response):
    if request.headers.get('Origin') in ORIGINS:
        response.headers['Access-Control-Allow-Origin']=request.headers['Origin']
        response.headers['Vary']='Origin'
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response

@app.get('/api/health')
def health():
    try:
        storage().ping()
    except Exception as exc:
        app.logger.error('contact_storage_unavailable:%s',type(exc).__name__)
        return jsonify(ok=False),503
    return jsonify(ok=True)

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='Your message is too long.'),413

@app.route('/api/contact', methods=['OPTIONS'])
def preflight():
    if request.headers.get('Origin') not in ORIGINS: return jsonify(error='Origin not allowed.'),403
    response=app.make_response(('',204))
    response.headers['Access-Control-Allow-Methods']='POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers']='Content-Type'
    response.headers['Access-Control-Max-Age']='600'
    return response

@app.route('/api/contact', methods=['POST'], provide_automatic_options=False)
def contact():
    if request.headers.get('Origin') not in ORIGINS:
        return jsonify(error='Please use the contact form on cookcredit.com.'),403
    if not request.is_json:
        return jsonify(error='JSON submission required.'),415
    try: data=fields(request.get_json(silent=True))
    except ValueError as exc: return jsonify(error=str(exc)),400
    fingerprint=hashlib.sha256(json.dumps({k:data[k] for k in ('name','email','message')},sort_keys=True).encode()).hexdigest()
    key='cc:contact:receipt:'+data['requestId']
    try:
        db=storage()
        previous=db.get(key)
        if previous:
            previous=json.loads(previous)
            if previous['hash']!=fingerprint: return jsonify(error='This submission changed. Reload before sending a new message.'),409
            if previous['state']=='sent': return jsonify(sent=True)
            return jsonify(error='Delivery is still pending or could not be confirmed. Please email connectwithus@cookcredit.com if needed.'),409
        # Shared Redis counters apply across workers, instances and restarts.
        email_hash=hashlib.sha256(data['email'].lower().encode()).hexdigest()
        for limit_key,maximum,ttl in [('cc:contact:global:hour',20,3600),('cc:contact:global:day',100,86400),('cc:contact:email:'+email_hash,3,3600)]:
            count=db.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",1,limit_key,ttl)
            if count>maximum:
                response=jsonify(error='Too many messages. Please try later or email connectwithus@cookcredit.com.');response.headers['Retry-After']='3600'
                return response,429
        pending=json.dumps({'hash':fingerprint,'state':'pending'})
        if not db.set(key,pending,nx=True,ex=86400): return jsonify(error='This message is already being processed.'),409
    except Exception as exc:
        app.logger.error('contact_storage_unavailable:%s',type(exc).__name__)
        return jsonify(error='Sending is temporarily unavailable. Your message has not been submitted. Please try later.'),503
    plain=f"Website contact message\n\nName: {data['name'] or 'Not supplied'}\nEmail: {data['email']}\n\n{data['message']}\n\nReference: {data['requestId']}"
    markup='<pre style="white-space:pre-wrap;font-family:Arial,sans-serif">'+html.escape(plain)+'</pre>'
    try:
        send_google_smtp(RECIPIENT,'CookCredit website contact',plain,markup)
        db.set(key,json.dumps({'hash':fingerprint,'state':'sent'}),ex=86400)
    except Exception:
        app.logger.error('contact_delivery_unconfirmed')
        # SMTP acceptance may be uncertain: retain the lease, do not auto-resend.
        return jsonify(error='We could not confirm delivery. Please email connectwithus@cookcredit.com if needed; your text is still in the form.'),503
    return jsonify(sent=True)
