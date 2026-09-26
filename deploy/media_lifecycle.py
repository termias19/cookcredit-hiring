"""Private applicant files expire; active company branding does not."""
APPLICANT_PREFIXES = ['skill_videos/', 'cookcredit-skill/', 'hiring_cv/']

def hiring_media_lifecycle():
    return {'rule': [{'action': {'type': 'Delete'},
                     'condition': {'age': 30, 'matchesPrefix': APPLICANT_PREFIXES}}]}
