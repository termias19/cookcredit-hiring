"""Presentation-only hiring results; preserve all capture controls and handlers."""
import re
from pathlib import Path
from hiring_capture_overlay import once


def apply_hiring_result(app, html, css):
    html = once(html, 'Hiring handoff', 'Your application')
    html = once(html, 'Submit this assessment</h3>', 'Review and submit</h3>')
    html = re.sub(r'(<p id="hiring-submit-copy">).*?(</p>)',
                  r'\1Review your recording, then send it and its measurements to the company for this application. A person reviews your work; the measurements are not independently verified.\2', html, count=1, flags=re.S)
    html = once(html, 'Return without submitting</button>', 'Back to application</button>')
    html = once(html, 'What the camera could measure</h2>', 'Recorded measurements</h2>')
    html = once(html, '<p class="eyebrow">Feedback breakdown</p>', '<p class="eyebrow">For employer review · out of 100</p>')
    panel = re.search(r'<section id="hiring-submit-panel".*?</section>', html, re.S).group(0)
    html = once(html, panel, '')
    anchor = '<article id="recording-card" class="recording-card" aria-labelledby="recording-heading" hidden>'
    html = once(html, anchor, anchor + '\n' + panel)
    app = once(app, 'Attaching the saved assessment to this application for server verification…',
               'Sending the recording and measurements to your application…')
    return app, html, css + '\n' + Path(__file__).with_name('hiring-result.css').read_text(encoding='utf-8')
