"""Record bounded administrative changes in the same transaction as the change.

Do not pass request bodies, invitation tokens, credentials or applicant evidence.
Existing applicant/evidence events remain in their original authoritative tables.
"""
from models.business import WorkspaceActivity


def record(session, org_id, actor_id, event_type, target_id, detail=None):
    session.add(WorkspaceActivity(org_id=org_id, actor_id=actor_id,
        event_type=event_type, target_id=str(target_id), detail=detail or {}))
