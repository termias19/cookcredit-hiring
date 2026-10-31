"""Versioned owner drafts, separate from publication and actual helper availability."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text
from models.home_service import HomeOperatingRules
from services import home_visits as visits

DAYS = ('mon','tue','wed','thu','fri','sat','sun')
STATES = frozenset('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())


def defaults():
    # Initial business direction only. No hours or travel buffer were approved;
    # an empty week stays closed and there is no activation endpoint here.
    return {'states':['GA'],'timeZone':'America/New_York','noticeHours':24,
            'shortNoticeHours':6,'bufferMinutes':None,'weeklyHours':[]}


def draft(session):
    row = session.get(HomeOperatingRules,1)
    return {'version':row.version if row else 0, 'rules':row.settings if row else defaults(),
            'published':False,'updatedAt':row.updated_at.isoformat() if row else None}


def validate(settings):
    visits.strict_object(settings,('states','timeZone','noticeHours','shortNoticeHours','bufferMinutes','weeklyHours'))
    states = settings['states']
    if not isinstance(states,list) or not 1<=len(states)<=10 or any(not isinstance(s,str) or s not in STATES for s in states):
        visits.fail('invalid_operating_rules','Choose valid US state abbreviations, such as GA.')
    zone = visits.bounded_text(settings['timeZone'],'the service timezone',64,required=True)
    try:ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError):visits.fail('invalid_operating_rules','Choose a valid service timezone.')
    notice,short = settings['noticeHours'],settings['shortNoticeHours']
    if type(notice)is not int or type(short)is not int or not 6<=short<=notice<=168:
        visits.fail('invalid_operating_rules','Use six hours to seven days of notice; short notice cannot exceed the default.')
    buffer = settings['bufferMinutes']
    if buffer is not None and (type(buffer)is not int or not 0<=buffer<=180 or buffer%15):
        visits.fail('invalid_operating_rules','Use a travel buffer from zero to 180 minutes in 15-minute steps.')
    hours = settings['weeklyHours']
    if not isinstance(hours,list) or len(hours)>7:
        visits.fail('invalid_operating_rules','Set at most one operating window per weekday.')
    seen=set();clean=[]
    for window in hours:
        visits.strict_object(window,('day','startMinute','endMinute'))
        day,start,end=window['day'],window['startMinute'],window['endMinute']
        if (not isinstance(day,str) or day not in DAYS or day in seen
            or type(start)is not int or type(end)is not int or not 0<=start<end<=1440 or start%15 or end%15):
            visits.fail('invalid_operating_rules','Check each weekday and its opening and closing times.')
        seen.add(day);clean.append({'day':day,'startMinute':start,'endMinute':end})
    clean.sort(key=lambda value:DAYS.index(value['day']))
    return {'states':sorted(set(states)),'timeZone':zone,'noticeHours':notice,'shortNoticeHours':short,
            'bufferMinutes':buffer,'weeklyHours':clean}


def save(session,principal,body):
    visits.strict_object(body,('version','rules'))
    if type(body['version'])is not int or body['version']<0:
        visits.fail('invalid_version','Refresh the operating rules before saving.')
    settings=validate(body['rules'])
    # Serialize first insert as well as later edits across two owner tabs.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'home-operating-rules'})
    row=session.get(HomeOperatingRules,1,populate_existing=True)
    current=row.version if row else 0
    if body['version']!=current:
        visits.fail('operating_rules_changed','Another edit changed these rules. Refresh before saving.',409)
    if row and row.settings==settings:return {'saved':True,'version':current,'published':False}
    if row:
        row.version+=1;row.settings=settings;row.updated_by=principal['uid'];row.updated_at=datetime.now(timezone.utc)
    else:
        row=HomeOperatingRules(id=1,version=1,settings=settings,updated_by=principal['uid'])
        session.add(row)
    # These are business settings, never household details. Preserve the exact
    # revision in the existing immutable event stream, with a pointer in access audit.
    visits.event(session,principal['uid'],'operating_rules_draft_saved',policyVersion=row.version,rules=settings)
    from services.home_customers import audit
    audit(session,principal,'operating_rules_draft_saved',row.version)
    return {'saved':True,'version':row.version,'published':False}
