"""Beam integration tests against a REAL Postgres + PostGIS.

Skipped unless DATABASE_URL points at a Postgres with PostGIS (the migration creates the extension).
Exercises the actual data-layer flow the routes drive — create a beam, fan it out to city-matched
cooks, a cook responds, the eater chooses, plus the PostGIS "cooks within range" query and the
lazy-expiry sweep — using the same models and queries as routes/beams.py.

Run locally:
  docker run -d --name cc-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=cookcredit -p 5544:5432 postgis/postgis:16-3.4
  cd backend && python migrations/run_migrations.py
  DATABASE_URL=postgresql://postgres:postgres@localhost:5544/cookcredit pytest tests/test_beams_integration.py -v
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs a Postgres+PostGIS (set DATABASE_URL) for the beam integration tests",
)

from sqlalchemy import func, text  # noqa: E402
from services.database import db_session, init_db  # noqa: E402
from models import User, EaterProfile, CookProfile, Beam, BeamResponse  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


def test_beam_flow_end_to_end():
    init_db()
    sfx = uuid.uuid4().hex[:8]
    eater_id, cook1_id, cook2_id = f"it_eat_{sfx}", f"it_cook1_{sfx}", f"it_cook2_{sfx}"
    city = f"Beamville_{sfx}"          # unique city so the fan-out matches only these two cooks

    try:
        # ── arrange: an eater + two approved, skill-verified cooks in the same city, with geo points
        with db_session() as s:
            s.add(User(id=eater_id, email=f"{eater_id}@t.com", name="Eater", roles=["eater"], active_role="eater"))
            s.add(User(id=cook1_id, email=f"{cook1_id}@t.com", name="Cook One", roles=["eater", "cook"], active_role="cook"))
            s.add(User(id=cook2_id, email=f"{cook2_id}@t.com", name="Cook Two", roles=["eater", "cook"], active_role="cook"))
            s.flush()
            s.add(EaterProfile(user_id=eater_id, address_city=city, address_state="GA"))
            for cid in (cook1_id, cook2_id):
                s.add(CookProfile(user_id=cid, base_city=city, base_state="GA", approved=True,
                                  skill_verified=True, cuisines=["Ethiopian"], price_per_hour=45,
                                  travel_radius_miles=20))
            s.flush()
            s.execute(text("UPDATE cook_profiles SET base_location=ST_MakePoint(-84.39,33.75)::geography WHERE user_id=:c"), {"c": cook1_id})
            s.execute(text("UPDATE cook_profiles SET base_location=ST_MakePoint(-84.40,33.76)::geography WHERE user_id=:c"), {"c": cook2_id})
            s.execute(text("UPDATE eater_profiles SET location=ST_MakePoint(-84.385,33.767)::geography WHERE user_id=:e"), {"e": eater_id})

        # ── act 1: create a beam and fan it out (mirrors routes.beams.create_beam)
        with db_session() as s:
            beam = Beam(eater_id=eater_id, craving_text="Doro wat tonight", scope="citywide",
                        city=city, state="GA", status="open", expires_at=_now() + timedelta(hours=24))
            s.add(beam); s.flush()
            beam_id = beam.id
            rows = (s.query(User.id)
                    .join(CookProfile, CookProfile.user_id == User.id)
                    .filter(CookProfile.approved.is_(True), CookProfile.skill_verified.is_(True),
                            func.lower(CookProfile.base_city) == city.lower(), User.id != eater_id)
                    .limit(200).all())
            cook_ids = [r[0] for r in rows]
            assert set(cook_ids) == {cook1_id, cook2_id}            # city match found both cooks
            for cid in cook_ids:
                s.add(BeamResponse(beam_id=beam_id, cook_id=cid, status="pending"))
            beam.matched_count = len(cook_ids)

        # ── act 2: cook1 responds with a note + price
        with db_session() as s:
            r = s.query(BeamResponse).filter_by(beam_id=beam_id, cook_id=cook1_id).first()
            r.status, r.note, r.price, r.responded_at = "responded", "I can cook that", 50, _now()

        # ── act 3: eater chooses cook1 (mirrors routes.beams.choose_responder)
        with db_session() as s:
            beam = s.get(Beam, beam_id)
            chosen = s.query(BeamResponse).filter_by(beam_id=beam_id, cook_id=cook1_id).first()
            assert chosen.status == "responded"
            (s.query(BeamResponse)
             .filter(BeamResponse.beam_id == beam_id, BeamResponse.status == "responded",
                     BeamResponse.id != chosen.id)
             .update({"status": "not_chosen"}, synchronize_session=False))
            chosen.status = "chosen"
            beam.status, beam.chosen_cook_id, beam.chosen_response_id = "fulfilled", cook1_id, chosen.id

        # ── assert: final lifecycle state
        with db_session() as s:
            beam = s.get(Beam, beam_id)
            assert beam.status == "fulfilled"
            assert beam.chosen_cook_id == cook1_id
            assert beam.matched_count == 2
            r1 = s.query(BeamResponse).filter_by(beam_id=beam_id, cook_id=cook1_id).first()
            r2 = s.query(BeamResponse).filter_by(beam_id=beam_id, cook_id=cook2_id).first()
            assert r1.status == "chosen"
            assert r2.status == "pending"          # never responded -> stays a pending recipient
            assert beam.to_dict()["chosenCookId"] == cook1_id

        # ── PostGIS: the "cooks within travel range of the eater" query (seed.py verify_geo pattern)
        with db_session() as s:
            res = s.execute(text("""
                SELECT cp.user_id
                FROM cook_profiles cp CROSS JOIN eater_profiles ep
                WHERE ep.user_id = :e AND cp.user_id IN (:c1, :c2)
                  AND ST_DWithin(cp.base_location, ep.location, cp.travel_radius_miles * 1609.34)
            """), {"e": eater_id, "c1": cook1_id, "c2": cook2_id}).fetchall()
            within = {row[0] for row in res}
            assert within == {cook1_id, cook2_id}

        # ── lazy expiry sweep flips an over-TTL open beam to 'expired'
        with db_session() as s:
            old = Beam(eater_id=eater_id, craving_text="stale", scope="citywide", city=city,
                       status="open", expires_at=_now() - timedelta(hours=1))
            s.add(old); s.flush()
            old_id = old.id
        with db_session() as s:
            s.query(Beam).filter(Beam.status == "open", Beam.expires_at <= _now()).update(
                {"status": "expired"}, synchronize_session=False)
        with db_session() as s:
            assert s.get(Beam, old_id).status == "expired"

    finally:
        # cleanup: deleting the users cascades to profiles, beams, and beam_responses
        with db_session() as s:
            for uid in (eater_id, cook1_id, cook2_id):
                u = s.get(User, uid)
                if u:
                    s.delete(u)
