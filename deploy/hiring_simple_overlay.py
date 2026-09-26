"""A compact hiring setup layered over the unchanged assessment capture."""
import re
from hiring_capture_overlay import once

PRESENTATION_JS = r'''
function renderHiringPresentation(presentation = {}) {
  const text = (id, value, fallback) => {
    const node = $(id);
    if (node) node.textContent = typeof value === 'string' && value.trim() ? value : fallback;
  };
  text('hiring-company-name', presentation.companyName, 'Your application');
  text('hiring-role-title', presentation.roleTitle, 'Knife skills assessment');
  text('hiring-instructions', presentation.instructions,
    'Keep your knife hand, blade and cutting board in view. Record 20–60 seconds at your normal, safe pace. Review your recording, then submit.');
  const logo = $('hiring-company-logo');
  if (logo) {
    logo.hidden = true; logo.removeAttribute('src');
    try {
      const url = new URL(presentation.logoUrl);
      if (url.protocol === 'https:' && !url.username && !url.password) {
        logo.alt = typeof presentation.companyName === 'string' ? presentation.companyName : 'Company logo';
        logo.referrerPolicy = 'no-referrer';
        logo.onload = () => { logo.hidden = false; };
        logo.onerror = () => { logo.hidden = true; };
        logo.src = url.href;
      }
    } catch { /* Keep the company name when no usable logo is configured. */ }
  }
  const name = $('m-subject');
  if (name && !name.value.trim() && typeof presentation.applicantName === 'string') {
    name.value = presentation.applicantName.slice(0, 120);
  }
}
'''

SIMPLE_CSS = '''
/* Hiring setup: one task, company context, then camera. */
body.hiring-experience {background:#F7F5F0;}
.hiring-experience #screen-splash {display:flex;flex-direction:column;max-width:760px;margin:auto;padding:24px clamp(18px,4vw,42px) 40px;gap:0;}
.hiring-experience #screen-splash .brand {width:100%;margin-bottom:28px;padding-bottom:16px;}
.hiring-experience #screen-splash .brand-actions {display:none;}
.hiring-experience #screen-splash .hiring-context-banner {max-width:none;width:100%;margin:0 0 24px;padding:0 0 24px;border:0;border-bottom:1px solid #DDD9CF;background:transparent;}
.hiring-company {display:flex;gap:14px;align-items:center;margin-bottom:12px;}
#hiring-company-logo {max-width:140px;max-height:64px;object-fit:contain;}
#hiring-company-name {font-size:14px;font-weight:600;margin:0;}
#screen-splash #hiring-role-title {font-family:Georgia,serif;font-size:clamp(28px,5vw,40px);font-weight:400;line-height:1.15;margin:8px 0 16px;}
#hiring-instructions {white-space:pre-wrap;overflow-wrap:anywhere;color:#454A42;line-height:1.65;margin:0 0 16px;}
.hiring-experience #screen-splash .hand-pick,.hiring-experience #screen-splash .meta-form {width:100%;max-width:none;margin:0 0 20px;}
.hiring-experience #screen-splash .hand-row {max-width:320px;}
.hiring-experience #screen-splash .hand-icon {width:28px;height:34px;}
.hiring-experience #screen-splash .hand-btn {padding:12px;min-height:0;}
.hiring-experience #screen-splash .meta-form {gap:14px;}
.hiring-experience #screen-splash .meta-form h2,.hiring-experience #screen-splash .form-intro,.hiring-experience #screen-splash .hand-note {display:none;}
.hiring-extra {border-top:1px solid #DDD9CF;padding-top:12px;}
.hiring-extra summary {cursor:pointer;color:#526057;font-size:14px;margin-bottom:12px;}
.hiring-extra label {display:block;margin-bottom:12px;}
.hiring-experience #screen-splash .splash-actions {width:100%;max-width:none;margin-top:0;}
.hiring-experience #screen-splash .privacy-note {font-size:12px;line-height:1.6;margin:16px 0;color:#625F58;}
'''

def apply_simple_hiring(app, html, css):
    app = once(app, 'async function configureHiringExperience()', PRESENTATION_JS + '\nasync function configureHiringExperience()')
    start = html.index('    <div class="intro-block">')
    end = html.index('    <!-- Two faces', start)
    privacy = re.search(r'<p class="privacy-note">.*?</p>', html[start:end], re.S).group(0)
    html = html[:start] + html[end:]
    start = html.index('      <p class="eyebrow">CookCredit hiring assessment</p>')
    end = html.index('      <div class="hiring-auth-row">', start)
    html = html[:start] + '''      <div class="hiring-company"><img id="hiring-company-logo" hidden alt=""><p id="hiring-company-name">Your application</p></div>
      <h1 id="hiring-role-title">Knife skills assessment</h1>
      <h2 id="hiring-context-heading" class="sr-only">Before you record</h2>
      <p id="hiring-instructions">Keep your knife hand, blade and cutting board in view. Record 20–60 seconds at your normal, safe pace. Review your recording, then submit.</p>
''' + html[end:]
    start = html.index('      <label>Camera angle')
    end = html.index('      <label class="consent biometric">', start)
    html = html[:start] + '<details class="hiring-extra"><summary>Optional recording details</summary>\n' + html[start:end] + '</details>\n' + html[end:]
    html = once(html, '    <p id="splash-status"', '    ' + privacy + '\n    <p id="splash-status"')
    html = once(html, '<title>CookCredit Skill | Camera-based knife feedback</title>', '<title>Knife skills assessment | CookCredit Hiring</title>')
    from hiring_result_overlay import apply_hiring_result
    return apply_hiring_result(app, html, css + '\n' + SIMPLE_CSS)
