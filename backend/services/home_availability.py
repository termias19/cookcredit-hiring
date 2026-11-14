"""Helper-owned hours over the existing models, serialized by the helper lock.

No public slot promises, permission grants, network calls or financial effects.
Original Mise weekday numbering is preserved: Sunday=0, Monday=1, Saturday=6.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, delete, text
from models import Booking, CookAvailability, CookBlockedDate
from models.home_service import HomeHelperPermission, HomeVisit
from services import home_visits as visits

DAYS=('sun','mon','tue','wed','thu','fri','sat')


def helper(session,uid,*,lock=False):
    row=session.get(HomeHelperPermission,uid,with_for_update=lock,populate_existing=lock)
    if not row or not row.enabled or not (row.cooking or row.cleaning):
        visits.fail('helper_approval_required','CookCredit helper access is required to manage availability.',403)
    return row


def validate(body):
    visits.strict_object(body,('version','timeZone','weeklyHours','blockedDates'))
    if type(body['version'])is not int or body['version']<0:
        visits.fail('invalid_version','Refresh your availability before saving.')
    zone=visits.bounded_text(body['timeZone'],'the schedule time zone',64,required=True)
    try:ZoneInfo(zone)
    except (ValueError,ZoneInfoNotFoundError):visits.fail('invalid_availability','Choose a valid schedule time zone.')
    hours=body['weeklyHours'];dates=body['blockedDates']
    if not isinstance(hours,list) or len(hours)>7:
        visits.fail('invalid_availability','Set at most one work window for each weekday.')
    seen=set();clean=[]
    for value in hours:
        visits.strict_object(value,('day','startHour','endHour'))
        day,start,end=value['day'],value['startHour'],value['endHour']
        if (not isinstance(day,str) or day not in DAYS or day in seen or type(start)is not int
            or type(end)is not int or not 0<=start<end<=24):
            visits.fail('invalid_availability','Check each weekday and its start and end hours.')
        seen.add(day);clean.append({'day':day,'startHour':start,'endHour':end})
    if not isinstance(dates,list) or len(dates)>60:
        visits.fail('invalid_availability','Choose at most 60 unavailable dates.')
    today=datetime.now(ZoneInfo(zone)).date();blocked=set()
    for value in dates:
        try:
            if not isinstance(value,str) or len(value)!=10:raise ValueError()
            day=date.fromisoformat(value)
            if not today<=day<=today+timedelta(days=365):raise ValueError()
        except (TypeError,ValueError):visits.fail('invalid_availability','Choose unavailable dates within the next year.')
        blocked.add(day.isoformat())
    return {'timeZone':zone,'weeklyHours':sorted(clean,key=lambda w:DAYS.index(w['day'])),
            'blockedDates':sorted(blocked)}


def read(session,uid,row=None):
    row=row or helper(session,uid)
    if row.availability_version>0 and not row.availability_time_zone:
        visits.fail('availability_unavailable','Please contact CookCredit to review this schedule.',503)
    zone=row.availability_time_zone or 'America/New_York'
    try:today=datetime.now(ZoneInfo(zone)).date()
    except (ValueError,ZoneInfoNotFoundError):visits.fail('availability_unavailable','Please contact CookCredit to review this schedule.',503)
    hours=session.execute(select(CookAvailability.day_of_week,CookAvailability.start_hour,CookAvailability.end_hour)
        .where(CookAvailability.cook_id==uid).order_by(CookAvailability.day_of_week).limit(8)).all()
    dates=session.execute(select(CookBlockedDate.blocked_date).where(CookBlockedDate.cook_id==uid,
        CookBlockedDate.blocked_date>=today).order_by(CookBlockedDate.blocked_date).limit(61)).scalars().all()
    # Unexpected legacy rows fail closed instead of silently truncating hours.
    if len(hours)>7 or len(dates)>60 or len({d for d,_,_ in hours})!=len(hours) or any(not 0<=d<=6 or not 0<=s<e<=24 for d,s,e in hours):
        visits.fail('availability_unavailable','Please contact CookCredit to review this schedule.',503)
    return {'version':row.availability_version,'configured':row.availability_version>0,
        'timeZone':zone,'weeklyHours':[{'day':DAYS[d],'startHour':s,'endHour':e}for d,s,e in hours],
        'blockedDates':[day.isoformat()for day in dates]}


def covers(settings,start,end):
    """Cover the entire elapsed interval, including both local dates at midnight.

    Convert UTC instants into schedule-local dates; use UTC comparisons because
    Python wall-clock subtraction can hide the extra hour at a DST fall-back.
    """
    zone=ZoneInfo(settings['timeZone']);windows={w['day']:w for w in settings['weeklyHours']}
    blocked=set(settings['blockedDates']);day=start.astimezone(zone).date()
    last=(end-timedelta(microseconds=1)).astimezone(zone).date();cursor=start
    while day<=last:
        if day.isoformat()in blocked:return False
        window=windows.get(DAYS[(day.weekday()+1)%7])
        if not window:return False
        opening=datetime.combine(day,time(),zone)+timedelta(hours=window['startHour'])
        closing=datetime.combine(day,time(),zone)+timedelta(hours=window['endHour'])
        opening,closing=opening.astimezone(timezone.utc),closing.astimezone(timezone.utc)
        if opening>cursor or closing<=cursor:return False
        cursor=min(end,closing)
        if cursor==end:return True
        # A later date cannot cover a gap before this date's midnight.
        if cursor!=datetime.combine(day+timedelta(days=1),time(),zone).astimezone(timezone.utc):return False
        day+=timedelta(days=1)
    return False


def require_available(session,uid,start,end):
    # Caller already holds HomeHelperPermission's FOR UPDATE lock. Assignment,
    # acceptance and schedule edits share this lock across all API instances.
    value=read(session,uid)
    if not value['configured']:
        visits.fail('helper_availability_required','Ask this helper to save their availability before assignment.',409)
    if not covers(value,start,end):
        visits.fail('helper_unavailable','This helper is unavailable for the full visit. Choose another time or helper.',409)


def save(session,principal,body):
    settings=validate(body);uid=principal['uid']
    if session.execute(text('SHOW transaction_isolation')).scalar_one()!='read committed':
        visits.fail('calendar_unavailable','Scheduling is temporarily unavailable. Please contact CookCredit.',503)
    row=helper(session,uid,lock=True)
    current=read(session,uid,row)
    if body['version']!=current['version']:
        visits.fail('availability_changed','Your availability changed in another window. Refresh before saving.',409)
    if row.availability_version and all(current[k]==v for k,v in settings.items()):
        return {'saved':True,'version':row.availability_version}
    now=datetime.now(timezone.utc);today=now.astimezone(ZoneInfo(settings['timeZone'])).date()
    assigned=session.execute(select(Booking.scheduled_date,Booking.scheduled_start_time,
        Booking.estimated_duration,HomeVisit.time_zone).join(HomeVisit,HomeVisit.booking_id==Booking.id)
        .where(Booking.cook_id==uid,Booking.status.notin_(('cancelled','completed')),
            Booking.scheduled_date>=today-timedelta(days=2),Booking.scheduled_date<=today+timedelta(days=367))
        .limit(501)).all()
    if len(assigned)>500:visits.fail('availability_review_required','Contact CookCredit to review your existing visits.',409)
    for day,start,hours,zone in assigned:
        begin=datetime.combine(day,start,ZoneInfo(zone)).astimezone(timezone.utc)
        end=begin+timedelta(minutes=int(hours*60))
        if end>now and not covers(settings,begin,end):
            visits.fail('availability_existing_visit','These hours conflict with an assigned visit. Ask CookCredit to arrange a change first.',409)
    # Bounded replacements affect only the helper's own scheduling preferences.
    # Existing booking, permission and immutable history rows are never deleted.
    session.execute(delete(CookAvailability).where(CookAvailability.cook_id==uid))
    session.execute(delete(CookBlockedDate).where(CookBlockedDate.cook_id==uid))
    session.add_all([CookAvailability(cook_id=uid,day_of_week=DAYS.index(w['day']),
        start_hour=w['startHour'],end_hour=w['endHour'])for w in settings['weeklyHours']])
    session.add_all([CookBlockedDate(cook_id=uid,blocked_date=date.fromisoformat(day))for day in settings['blockedDates']])
    row.availability_version+=1;row.availability_time_zone=settings['timeZone']
    from services.home_customers import audit
    audit(session,principal,'helper_availability_saved',uid)
    # Do not copy exact working dates or personal reasons into generic events.
    visits.event(session,uid,'helper_availability_saved',scheduleVersion=row.availability_version,
        weeklyWindowCount=len(settings['weeklyHours']),blockedDateCount=len(settings['blockedDates']))
    return {'saved':True,'version':row.availability_version}
