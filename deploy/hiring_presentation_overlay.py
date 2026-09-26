"""Hiring-only presentation; never changes the learning page or measurement code."""
from pathlib import Path
from hiring_capture_overlay import once
from hiring_simple_overlay import apply_simple_hiring


def apply_presentation(app, html, css):
    app = once(app, "  const formOk = !!state.knifeHand", "  const hiringNameMissing = !!state.hiring && !$('m-subject').value.trim();\n  const formOk = !hiringNameMissing && !!state.knifeHand")
    app = once(app, "    : ok ? 'Ready.", "    : hiringNameMissing ? 'Enter your full name to continue with your application.'\n    : ok ? 'Ready.")
    html = once(html, 'content="dark"', 'content="light"')
    html = once(html, 'content="#090a09"', 'content="#F7F5F0"')
    html = once(html, 'A few details help the feedback make sense. Your name or initials are optional.', 'Use the same full name as your job application. Your measurements use the same method for everyone.')
    html = once(html, 'Name or initials <span class="optional">Optional</span>', 'Full name <span class="optional">Required</span>')
    html = once(html, 'id="m-subject" type="text" autocomplete="off" maxlength="32"', 'id="m-subject" type="text" autocomplete="name" maxlength="120" required')
    html = once(html, 'placeholder="Shown only in your downloaded report"', 'placeholder="Your full name"')
    html = once(html, 'See your knife work more clearly.', 'Show your knife work.')
    html = once(html, 'CookCredit Skill / Private beta', 'COOKCREDIT / HIRING')
    return apply_simple_hiring(app, html, css + '\n' + Path(__file__).with_name('hiring-presentation.css').read_text(encoding='utf-8'))
