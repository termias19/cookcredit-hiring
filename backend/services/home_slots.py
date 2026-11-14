"""Bounded advisory times over existing Home schedules and active Bookings.

No helper identity, exact capacity, household address, reservation or provider
request leaves this module. Creation/assignment must recheck current policy.
"""
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from sqlalchemy import select,text
from models import CookProfile,CookAvailability,CookBlockedDate
from models.home_service import HomeHelperPermission
from services import home_operating_rules as rules,home_availability as availability,home_visits as visits

MAX_HELPERS=100


def suggestions(session,query,*,customer_id=None):
    if set(query)-{'date','service','durationMinutes','state'}:
        visits.fail('invalid_slot_query','Choose a date, service and visit length.')
    if hasattr(query,'getlist') and any(len(query.getlist(key))!=1 for key in query):
        visits.fail('invalid_slot_query','Choose one date, service and visit length.')
    policy=rules.active(session)
    settings=policy['rules'];zone=ZoneInfo(settings['timeZone']);now=datetime.now(timezone.utc)
    try:
        raw=query.get('date');day=date.fromisoformat(raw)
        raw_minutes=query.get('durationMinutes')
        if not isinstance(raw,str) or day.isoformat()!=raw or not isinstance(raw_minutes,str) or not raw_minutes.isascii() or not raw_minutes.isdecimal():raise ValueError()
        duration=int(raw_minutes)
        if not 60<=duration<=480 or duration%30:raise ValueError()
        today=now.astimezone(zone).date()
        if not today<=day<=today+timedelta(days=30):raise ValueError()
    except (TypeError,ValueError):
        visits.fail('invalid_slot_query','Choose a date within 30 days and one to eight hours in half-hour steps.')
    service=query.get('service')
    if service not in ('cooking','cleaning','both'):visits.fail('invalid_slot_query','Choose cooking, cleaning or both.')
    state=query.get('state')
    if state is None and len(settings['states'])==1:state=settings['states'][0]
    if state not in settings['states']:
        visits.fail('service_area_review_required','Choose a state in CookCredit’s service area; exact local coverage needs review.',409)
    result={'date':day.isoformat(),'timeZone':settings['timeZone'],'policyVersion':policy['version'],
        'slots':[],'reviewRequired':True,'reservesTime':False,'areaReviewRequired':True}
    window=next((w for w in settings['weeklyHours']if w['day']==rules.DAYS[day.weekday()]),None)
    if window is None:return result
    candidates=[]
    for minute in range(window['startMinute'],window['endMinute'],30):
        start=datetime.combine(day,time(),zone)+timedelta(minutes=minute)
        # Never silently offer an ambiguous/nonexistent local clock time.
        if start.utcoffset()!=start.replace(fold=1).utcoffset():continue
        if start.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=start.replace(tzinfo=None):continue
        start=start.astimezone(timezone.utc);end=start+timedelta(minutes=duration)
        if start<now+timedelta(hours=settings['noticeHours']) or not rules.window_covers(policy,start,end):continue
        candidates.append((minute,start,end))
    if not candidates:return result
    query_helpers=select(HomeHelperPermission.user_id,HomeHelperPermission.availability_time_zone).outerjoin(
        CookProfile,CookProfile.user_id==HomeHelperPermission.user_id).where(
            HomeHelperPermission.enabled.is_(True),HomeHelperPermission.availability_version>0,
            HomeHelperPermission.availability_time_zone.is_not(None))
    if customer_id is not None:query_helpers=query_helpers.where(HomeHelperPermission.user_id!=customer_id)
    if service in ('cooking','both'):
        query_helpers=query_helpers.where(HomeHelperPermission.cooking.is_(True),CookProfile.approved.is_(True))
    if service in ('cleaning','both'):query_helpers=query_helpers.where(HomeHelperPermission.cleaning.is_(True))
    helpers=session.execute(query_helpers.order_by(HomeHelperPermission.user_id).limit(MAX_HELPERS)).all()
    if not helpers:return result
    ids=[uid for uid,_ in helpers]
    hours=session.execute(select(CookAvailability.cook_id,CookAvailability.day_of_week,
        CookAvailability.start_hour,CookAvailability.end_hour).where(CookAvailability.cook_id.in_(ids))
        .order_by(CookAvailability.cook_id,CookAvailability.day_of_week).limit(MAX_HELPERS*7+1)).all()
    if len(hours)>MAX_HELPERS*7:
        visits.fail('availability_unavailable','Please contact CookCredit to review availability.',503)
    blocked=session.execute(select(CookBlockedDate.cook_id,CookBlockedDate.blocked_date).where(
        CookBlockedDate.cook_id.in_(ids),CookBlockedDate.blocked_date>=day-timedelta(days=2),
        CookBlockedDate.blocked_date<=day+timedelta(days=2))).all()
    first=min(begin for _,begin,_ in candidates);last=max(end for _,_,end in candidates)
    gap=timedelta(minutes=rules.buffer_minutes(policy))
    # Same half-open elapsed-time and travel margin used by assignment. Date
    # bounds keep the existing helper/date index usable; the UTC predicates
    # discard unrelated days before the bounded row materialization.
    commitments=session.execute(text(f'''SELECT b.cook_id,
        {rules.COMMITMENT_START_SQL} AS begins,{rules.COMMITMENT_END_SQL} AS ends
        FROM bookings b JOIN home_visits v ON v.booking_id=b.id
        WHERE b.cook_id=ANY(:helpers) AND ({rules.COMMITMENT_CANDIDATES_SQL})
        AND ({rules.COMMITMENT_START_SQL})<:last_time
        AND ({rules.COMMITMENT_END_SQL})>:first_time LIMIT 5001'''),
        {'helpers':ids,'first_day':day-timedelta(days=2),'last_day':day+timedelta(days=2),
         'first_time':first-gap,'last_time':last+gap,'gap_minutes':rules.buffer_minutes(policy)}).all()
    if len(commitments)>5000:visits.fail('availability_unavailable','Please contact CookCredit to review availability.',503)
    schedules={uid:{'timeZone':tz,'weeklyHours':[],'blockedDates':[]}for uid,tz in helpers}
    for uid,weekday,start,end in hours:
        if not 0<=weekday<=6 or not 0<=start<end<=24:
            visits.fail('availability_unavailable','Please contact CookCredit to review availability.',503)
        schedules[uid]['weeklyHours'].append({'day':availability.DAYS[weekday],'startHour':start,'endHour':end})
    for uid,day_off in blocked:schedules[uid]['blockedDates'].append(day_off.isoformat())
    intervals={uid:[]for uid in ids}
    for uid,begin,end in commitments:
        intervals[uid].append((begin,end))
    usable=[]
    for uid,settings in schedules.items():
        days=[value['day']for value in settings['weeklyHours']]
        if len(days)!=len(set(days)):continue
        try:ZoneInfo(settings['timeZone'])
        except (ValueError,ZoneInfoNotFoundError):continue
        usable.append((uid,settings))
    for minute,start,end in candidates:
        if any(availability.covers(settings,start,end) and
            not any(begin<end+gap and finish>start-gap for begin,finish in intervals[uid])for uid,settings in usable):
            result['slots'].append({'time':f'{minute//60:02d}:{minute%60:02d}','durationMinutes':duration})
    return result
