"""Add CookCredit learning/hiring pages without replacing existing website assets.

Preparation and publishing are separate. Publish rechecks the recorded live
version, preserves every unrelated hash, and stores the rollback version.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import requests
from hiring_staging import client, api

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent/'work/cookcredit-main-hiring-entry'
OUT = ROOT/'public-site'
SITE = 'foodnlit-1123e'
CONTACT_ORIGIN = 'https://cookcredit-contact-915097816203.us-central1.run.app'
HOSTING = 'https://firebasehosting.googleapis.com/v1beta1/'
ALLOWED = {'/about/index.html', '/contact/index.html', '/contact-form.js', '/index.html', '/learn/index.html', '/hiring/index.html', '/cookcredit-entry.css',
           '/sitemap.xml', '/cookcredit-mark-orange.svg', '/cookcredit-mark-orange.png',
           '/site-navigation.js', '/media/knife-analysis-showcase.mp4', '/media/knife-analysis-showcase.jpg'}


def prepare():
    inventory = json.loads((WORK.parent/'launch-inventory.json').read_text())['mainSite']
    original = (WORK/'live-index.html').read_text(encoding='utf-8')
    OUT.mkdir(exist_ok=True)
    header = original[original.index('  <header'):original.index('  <main')]
    header = header.replace('href="#', 'href="/#')
    header = header.replace('<a href="/#products">Products</a>',
        '<a href="/learn/">Learn &amp; practise</a>\n      <a href="/hiring/">For hiring managers</a>\n      <a href="/#products">Products</a>')
    footer = original[original.index('  <footer'):original.index('  <script src="/main.js"')]
    footer = footer.replace('<a href="/privacy.html">', '<a href="/learn/">Learn</a><a href="/hiring/">Hiring</a><a href="/privacy.html">')
    def page(slug, title, description, content):
        structured = {'@context':'https://schema.org','@type':'WebPage','name':title,
                      'url':f'https://cookcredit.com/{slug}/','description':description,
                      'isPartOf':{'@id':'https://cookcredit.com/#website'}}
        return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><meta name="description" content="{description}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="https://cookcredit.com/{slug}/">
<link rel="icon" type="image/svg+xml" href="/cookcredit-mark-orange.svg">
<meta property="og:type" content="website"><meta property="og:site_name" content="CookCredit">
<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">
<meta property="og:url" content="https://cookcredit.com/{slug}/"><meta property="og:image" content="https://cookcredit.com/poster.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/cookcredit-entry.css">
<script type="application/ld+json">{json.dumps(structured, ensure_ascii=False)}</script>
</head><body class="entry-page"><a class="skip-link" href="#main">Skip to main content</a>
{header}<main id="main">{content}</main>{footer}<script src="/main.js" defer></script></body></html>'''
    hiring = '''
<section class="entry-hero"><div><p class="eyebrow">CookCredit / For hiring managers</p>
<h1>See the skill.<br>Know the cook.</h1>
<p class="entry-summary">Bring a practical knife-skills assessment into the hiring process you already use. Give every applicant a clear task, then review the work behind their result.</p>
<div class="entry-actions"><a class="button button-dark" href="https://cookcredit-hiring-staging.web.app/request-access">Request hiring access</a><a class="text-link" href="#how-it-works">See how it works ↓</a></div>
<p class="entry-note">Hiring is in invited testing. Public self-service and subscriptions are not open yet.</p>
<a class="entry-small-link" href="https://cookcredit-hiring-staging.web.app/business/roles">Already invited? Sign in to your workspace →</a>
</div><figure class="entry-image"><img src="/poster.jpg" alt="A cook practising knife work at a cutting board" width="960" height="720"><figcaption>A real work sample, with the recording available for review.</figcaption></figure></section>
<section class="entry-section" id="how-it-works"><p class="eyebrow">One task. A clearer conversation.</p><h2>From application to evidence.</h2>
<ol class="entry-steps"><li><span>01</span><div><h3>Set the requirements</h3><p>Choose the applicant details you need, your knife-skill criteria, and whether to allow up to three attempts.</p></div></li>
<li><span>02</span><div><h3>Invite a practical demonstration</h3><p>Applicants open your branded link, review the sharing notice, and record the existing CookCredit knife assessment.</p></div></li>
<li><span>03</span><div><h3>Review the work</h3><p>Open the submitted video alongside rhythm, consistency and form. See the attempt history and decide who moves forward.</p></div></li></ol>
<p class="entry-note">During testing, results require human review. Automatic pass/fail screening is not enabled while independent video verification is being validated.</p></section>
<section class="entry-section entry-split"><div><p class="eyebrow">Evidence you can inspect</p><h2>A score should start a conversation.</h2><p>Understand what was measured, watch the recording, and compare it with the needs of your kitchen. Knife-work feedback is one part of evaluating a cook.</p><a class="text-link" href="https://cookcredit-knife-demo.web.app/">Try the published assessment ↗</a><p class="entry-note">Trying this link does not submit an application.</p></div>
<dl class="entry-measures"><div><dt>Rhythm</dt><dd>The timing between detected cutting strokes.</dd></div><div><dt>Consistency</dt><dd>How repeatable the detected movements are.</dd></div><div><dt>Form</dt><dd>The assessment’s movement-based form feedback.</dd></div><div><dt>Recording</dt><dd>The applicant’s shared video, available to the reviewing employer.</dd></div></dl></section>
<section class="entry-section" id="integrations"><p class="eyebrow">Fits your hiring process</p><h2>Your brand. Your workflow.</h2>
<div class="entry-integrations"><article><p class="entry-number">01 / Branded link</p><h3>Add a link anywhere.</h3><p>Place an assessment invitation in an application, careers page or candidate message. Add your company logo and colors.</p></article>
<article><p class="entry-number">02 / Embedded widget</p><h3>Keep the experience close.</h3><p>Place the application entry on your own website. The recording step uses the published CookCredit assessment.</p></article>
<article><p class="entry-number">03 / API + webhooks</p><h3>Connect your hiring software.</h3><p>Request assessments and receive signed status updates. Integration depends on the permissions and capabilities of your hiring platform.</p></article></div>
<p class="entry-note">These integrations are available for invited testing. Contact us to review your platform and setup.</p></section>
<section class="entry-section entry-close"><p class="eyebrow">Built around practical skills</p><h2>Make the next hire more informed.</h2><p>Tell us about your kitchen and the hiring tools you use.</p><a class="button button-dark" href="mailto:connectwithus@cookcredit.com?subject=CookCredit%20hiring%20access">Talk to CookCredit</a></section>'''
    learn = '''
<section class="entry-hero"><div><p class="eyebrow">CookCredit / Learn &amp; practise</p><h1>Good knife work<br>takes practice.</h1>
<p class="entry-summary">See your movement more clearly. Use CookCredit’s published knife assessment to practise, review feedback, and choose what to work on next.</p>
<div class="entry-actions"><a class="button button-dark" href="https://cookcredit-knife-demo.web.app/">Start practising ↗</a><a class="text-link" href="#your-session">Explore the session ↓</a></div>
<p class="entry-note">Opens the existing CookCredit assessment. A practice session does not apply for a job or share a recording with an employer.</p></div>
<figure class="entry-image"><img src="/poster.jpg" alt="Knife work on a cutting board during a cooking session" width="960" height="720"><figcaption>Practical feedback, grounded in the work you do.</figcaption></figure></section>
<section class="entry-section" id="your-session"><p class="eyebrow">Your next practice session</p><h2>Try. Observe. Try again.</h2>
<ol class="entry-steps"><li><span>01</span><div><h3>Set up your workspace</h3><p>Follow the assessment’s camera and setup instructions. Make sure your work is clearly visible before starting.</p></div></li>
<li><span>02</span><div><h3>Practise at your own pace</h3><p>Use the published experience to observe your knife movement and complete a session.</p></div></li>
<li><span>03</span><div><h3>Review what happened</h3><p>Look at rhythm, consistency and form feedback. Review your recording and pick one specific part of your technique to practise.</p></div></li></ol></section>
<section class="entry-section entry-split"><div><p class="eyebrow">For learners and educators</p><h2>Make progress visible.</h2><p>CookCredit gives you another way to look at practical work. Camera position and visibility affect measurements; use the feedback alongside instruction and your own review.</p><a class="button button-dark" href="https://cookcredit-knife-demo.web.app/">Open the knife assessment ↗</a></div>
<div class="entry-aside"><h3>Applying for a kitchen role?</h3><p>Use the invitation your employer sends you. That link connects the assessment to the correct role and asks you to review what will be shared.</p><a class="text-link" href="/hiring/">How CookCredit hiring works →</a><p class="entry-note">A practice result is not a professional qualification or a verified hiring decision.</p></div></section>'''
    for slug, title, description, content in [
        ('hiring', 'CookCredit for hiring | Practical knife-skills assessments', 'Bring knife-skills assessments into chef and cook hiring with branded links, an embedded entry, or API and webhooks. Explore CookCredit hiring.', hiring),
        ('learn', 'Learn and practise knife skills | CookCredit', 'Practise knife skills with CookCredit. Review rhythm, consistency, form and your recording in the published knife assessment.', learn),
    ]:
        directory = OUT/slug; directory.mkdir(exist_ok=True)
        (directory/'index.html').write_text(page(slug,title,description,content),encoding='utf-8')
    draft = original.replace('      <a href="#products">Products</a>',
        '      <a href="/learn/">Learn &amp; practise</a>\n      <a href="/hiring/">For hiring managers</a>\n      <a href="#products">Products</a>')
    draft = draft.replace('Try CookCredit Skill</a>', 'Learn &amp; practise</a>').replace('href="https://cookcredit-knife-demo.web.app" target="_blank" rel="noopener">Learn', 'href="/learn/">Learn')
    draft = draft.replace('<a class="button button-ghost" href="https://toque.cookcredit.com">', '<a class="button button-ghost" href="/hiring/">For hiring managers</a>\n          <a class="button button-ghost" href="https://toque.cookcredit.com">')
    draft = draft.replace('<link rel="stylesheet" href="/style.css">','<link rel="stylesheet" href="/style.css">\n  <link rel="stylesheet" href="/cookcredit-entry.css">')
    (OUT/'index.html').write_text(draft,encoding='utf-8')
    xml = (WORK/'live-sitemap.xml').read_text(encoding='utf-8')
    xml = xml.replace('</urlset>', '<url><loc>https://cookcredit.com/learn/</loc></url>\n<url><loc>https://cookcredit.com/hiring/</loc></url>\n</urlset>')
    ET.fromstring(xml)
    (OUT/'sitemap.xml').write_text(xml,encoding='utf-8')
    for extension in ('svg','png'):
        shutil.copyfile(ROOT/f'frontend/public/cookcredit-mark-orange.{extension}',OUT/f'cookcredit-mark-orange.{extension}')
    (WORK/'public-entry-release.json').write_text(json.dumps({'baseline':inventory,'published':False},indent=2))
    print('Prepared CookCredit public HTML, sitemap, and orange email assets. No release yet.')


def publish():
    # Never publish a contact form whose delivery service is not available.
    contact_html=(OUT/'contact/index.html').read_text(encoding='utf-8')
    assert f'data-endpoint="{CONTACT_ORIGIN}/api/contact"' in contact_html
    health=requests.get(CONTACT_ORIGIN+'/api/health',timeout=30)
    assert health.status_code==200 and health.json().get('ok') is True, 'Contact service is not ready'
    preflight=requests.options(CONTACT_ORIGIN+'/api/contact',headers={'Origin':'https://cookcredit.com','Access-Control-Request-Method':'POST'},timeout=30)
    assert preflight.status_code==204 and preflight.headers.get('Access-Control-Allow-Origin')=='https://cookcredit.com', 'Contact CORS is not ready'
    report=json.loads((WORK/'public-entry-release.json').read_text())
    session=client()
    if report['published']:
        latest=api(session,'GET',HOSTING+f'sites/{SITE}/releases',params={'pageSize':1})['releases'][0]
        assert latest['name']==report['release'], 'A different release changed the site; review again'
        current=api(session,'GET',HOSTING+report['version'])
        report['baseline']={'version':report['version'],'release':report['release'],
                            'config':current.get('config',{}),'paths':report['publishedPaths']}
    def unchanged():
        latest=api(session,'GET',HOSTING+f'sites/{SITE}/releases',params={'pageSize':1})['releases'][0]
        assert latest['version']['name']==report['baseline']['version'], 'Live site changed; review again'
    unchanged()
    paths=copy.deepcopy(report['baseline']['paths']); blobs={}; sources={}
    for path in OUT.rglob('*'):
        if not path.is_file(): continue
        url='/'+path.relative_to(OUT).as_posix()
        assert url in ALLOWED, 'Unexpected public asset: '+url
        body=path.read_bytes(); compressed=gzip.compress(body,mtime=0)
        digest=hashlib.sha256(compressed).hexdigest()
        paths[url]=digest; blobs[digest]=compressed; sources[url]=hashlib.sha256(body).hexdigest()
    assert set(sources)==ALLOWED
    config=copy.deepcopy(report['baseline']['config'])
    hashes=[]
    for path in OUT.rglob('*.html'):
        for script in re.findall(r'<script type="application/ld\+json">(.*?)</script>',path.read_text(encoding='utf-8'),re.S):
            import base64
            hashes.append("'sha256-"+base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()+"'")
    for header in config['headers']:
        csp=header['headers'].get('Content-Security-Policy')
        if csp:
            header['headers']['Content-Security-Policy']=csp.replace("script-src 'self'", "script-src 'self' "+' '.join(sorted(set(hashes)-{h for h in hashes if h in csp})))
    for glob in ['/learn/**','/hiring/**','/about/**','/contact/**']:
        if not any(h.get('glob')==glob for h in config['headers']):
            config['headers'].append({'glob':glob,'headers':{'Cache-Control':'no-cache'}})
    contact_headers=next(h['headers'] for h in config['headers'] if h.get('glob')=='/contact/**')
    csp=next(h['headers']['Content-Security-Policy'] for h in config['headers'] if h.get('glob')!='/contact/**' and 'Content-Security-Policy' in h['headers'])
    contact_headers['Content-Security-Policy']=csp.replace("connect-src 'self';", "connect-src 'self' "+CONTACT_ORIGIN+";")
    version=api(session,'POST',HOSTING+f'sites/{SITE}/versions',json={'config':config})
    population=api(session,'POST',HOSTING+version['name']+':populateFiles',json={'files':paths})
    assert all(digest in blobs for digest in population.get('uploadRequiredHashes',[])), 'Unrelated asset was not preserved'
    upload=population['uploadUrl']; assert upload.startswith('https://upload-firebasehosting.googleapis.com/upload/sites/'+SITE+'/')
    for digest in population.get('uploadRequiredHashes',[]):
        response=session.post(upload+'/'+digest,data=blobs[digest],headers={'Content-Type':'application/octet-stream'},timeout=60)
        response.raise_for_status()
    api(session,'PATCH',HOSTING+version['name'],params={'updateMask':'status'},json={'status':'FINALIZED'})
    listing=api(session,'GET',HOSTING+version['name']+'/files',params={'pageSize':1000})
    assert not listing.get('nextPageToken') and {i['path']:i['hash'] for i in listing['files']}==paths
    unchanged()
    release=api(session,'POST',HOSTING+f'sites/{SITE}/releases',params={'versionName':version['name']},
                json={'message':'CookCredit learning and hiring entry pages; preserve existing products, assessment and legal pages'})
    report.update(published=True,release=release['name'],version=version['name'],publishedPaths=paths,
                  sourceHashes=sources,rollbackVersion=report.get('rollbackVersion',report['baseline']['version']))
    (WORK/'public-entry-release.json').write_text(json.dumps(report,indent=2))
    changed=[p for p,h in report['baseline']['paths'].items() if paths[p]!=h]
    print(json.dumps({'published':True,'release':release['name'],'changedExistingPaths':changed,
                      'preservedExistingAssets':len(report['baseline']['paths'])-len(changed)}))


def verify():
    report=json.loads((WORK/'public-entry-release.json').read_text())
    assert report['published']
    results={}
    for path,digest in report['sourceHashes'].items():
        public=path.removesuffix('index.html') if path.endswith('/index.html') else path
        response=requests.get('https://cookcredit.com'+public,timeout=30)
        response.raise_for_status()
        assert hashlib.sha256(response.content).hexdigest()==digest, public+' content differs'
        assert 'noindex' not in response.headers.get('X-Robots-Tag','')
        results[public]=response.status_code
    report['httpVerified']=results
    (WORK/'public-entry-release.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(results))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['prepare','publish','verify'])
    globals()[parser.parse_args().phase]()
