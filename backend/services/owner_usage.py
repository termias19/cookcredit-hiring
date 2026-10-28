"""Owner-only aggregates from existing Hiring records; no new event collection."""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from services.hiring_access import OWNER_EMAIL


def test_emails():
    # Explicit acceptance identities belong in runtime configuration, not public Git.
    return sorted({OWNER_EMAIL} | {e.strip().casefold() for e in
        os.getenv('HIRING_USAGE_TEST_EMAILS', '').split(',') if e.strip()})


# Actors join real account rows, excluding worker/system actors. Activity is a
# lower bound: passive page views and persistent login sessions are not tracked.
QUERY = text("""
WITH events AS (
 SELECT id AS uid, created_at AS at, 'signups' AS metric, id::text AS item FROM users
 UNION ALL SELECT applicant_id, submitted_at, 'applications', id::text FROM hiring_applications
 UNION ALL SELECT applicant_id, started_at, 'activeUsers', id::text FROM hiring_assessment_sessions
 UNION ALL SELECT applicant_id, completed_at, 'completedAssessments', id::text FROM hiring_assessment_sessions
 UNION ALL SELECT applicant_id, granted_at, 'activeUsers', id::text FROM assessment_shares
 UNION ALL SELECT viewer_id, accessed_at, 'activeUsers', id::text FROM assessment_access_log
 UNION ALL SELECT actor_id, created_at, 'activeUsers', id::text FROM workspace_activity
 UNION ALL SELECT actor_id, created_at, 'activeUsers', id::text FROM hiring_application_events
 UNION ALL SELECT actor_id, created_at, 'activeUsers', id::text FROM hiring_access_events
), scoped AS (
 SELECT e.*, floor(extract(epoch FROM (e.at - CAST(:start AS timestamptz))) / 604800)::int AS week,
 CASE WHEN lower(u.email) = ANY(CAST(:test_emails AS text[]))
       OR lower(u.email) LIKE '%@example.test' OR lower(u.email) LIKE '%@example.com'
      THEN 'test' ELSE 'other' END AS cohort
 FROM events e JOIN users u ON u.id = e.uid
 WHERE e.at >= CAST(:start AS timestamptz) AND e.at < CAST(:end AS timestamptz)
)
SELECT week, cohort, count(DISTINCT uid) AS "activeUsers",
 count(DISTINCT item) FILTER (WHERE metric = 'signups') AS signups,
 count(DISTINCT item) FILTER (WHERE metric = 'applications') AS applications,
 count(DISTINCT item) FILTER (WHERE metric = 'completedAssessments') AS "completedAssessments"
FROM scoped GROUP BY week, cohort ORDER BY week, cohort
""")


def snapshot(session, *, now=None):
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=28)
    # Bounded on-demand query. No polling, materialized duplicate or per-user export.
    session.execute(text('SET TRANSACTION READ ONLY'))
    session.execute(text('SET LOCAL statement_timeout = 5000'))
    rows = session.execute(QUERY, {'start': start, 'end': end, 'test_emails': test_emails()}).mappings()
    empty = lambda: dict(activeUsers=0, signups=0, applications=0, completedAssessments=0)
    weeks = [dict(start=(start + timedelta(days=7*i)).isoformat(),
                  end=(start + timedelta(days=7*(i+1))).isoformat(), other=empty(), test=empty())
             for i in range(4)]
    for row in rows:
        weeks[row['week']][row['cohort']] = {key: int(row[key]) for key in empty()}
    return dict(generatedAt=end.isoformat(), weeks=list(reversed(weeks)),
                testClassification='Owner, configured acceptance accounts and reserved example domains. Other accounts may still include unclassified tests.',
                activityDefinition='Distinct accounts with recorded Hiring actions. Excludes anonymous visitors and passive visits. Weekly counts cannot be added to obtain unique monthly users.')
