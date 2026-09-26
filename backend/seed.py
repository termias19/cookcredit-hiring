"""
CookCredit seed script — creates test data for local development.

Usage:
  cd backend
  python seed.py

Requires DATABASE_URL in .env (e.g. postgresql://postgres:password@localhost:5432/cookcredit)
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from services.database import db_session, init_db
from sqlalchemy import text


SEED_SQL = """
-- ══════════════════════════════════════════════════════════════════════════════
-- USERS
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO users (id, email, name, phone, roles, active_role) VALUES
  ('cook_aisha',   'aisha@test.com',   'Aisha Mohammed', '+14045551001', '{eater,cook}', 'cook'),
  ('cook_marcus',  'marcus@test.com',  'Marcus Williams', '+14045551002', '{eater,cook}', 'cook'),
  ('eater_sarah',  'sarah@test.com',   'Sarah Chen',      '+14045551003', '{eater}',      'eater'),
  ('eater_david',  'david@test.com',   'David Park',      '+14045551004', '{eater}',      'eater'),
  ('eater_jordan', 'jordan@test.com',  'Jordan Rivera',   '+14045551005', '{eater}',      'eater')
ON CONFLICT (id) DO NOTHING;

-- ══════════════════════════════════════════════════════════════════════════════
-- COOK PROFILES
-- Atlanta coords: 33.749, -84.388
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO cook_profiles (
  user_id, bio, specialties, cuisines, price_per_hour, travel_radius_miles,
  base_location, base_city, base_state, years_experience, dietary_capabilities, approved
) VALUES
  ('cook_aisha',
   'Born in Addis Ababa, I bring the flavors of Ethiopia and Eritrea to your kitchen. From injera to doro wat, I cook what my grandmother taught me.',
   '{Ethiopian,Eritrean}', '{Ethiopian,Eritrean,East African}',
   45.00, 15.0,
   ST_MakePoint(-84.3880, 33.7490)::geography,
   'Atlanta', 'GA', 8, '{halal,gluten-free}', true),

  ('cook_marcus',
   'Third-generation Southern cook. Smoked meats, scratch biscuits, and greens that''ll make you call your mama.',
   '{Southern,BBQ,Soul Food}', '{Southern,Soul Food,BBQ}',
   55.00, 20.0,
   ST_MakePoint(-84.4000, 33.7600)::geography,
   'Atlanta', 'GA', 12, '{gluten-free}', true)
ON CONFLICT (user_id) DO NOTHING;

-- ══════════════════════════════════════════════════════════════════════════════
-- EATER PROFILES
-- Spread around Atlanta metro
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO eater_profiles (user_id, address_street, address_city, address_state, address_zip, location) VALUES
  ('eater_sarah',  '123 Peachtree St NE', 'Atlanta', 'GA', '30309',
   ST_MakePoint(-84.3853, 33.7676)::geography),
  ('eater_david',  '456 Ponce de Leon Ave', 'Atlanta', 'GA', '30308',
   ST_MakePoint(-84.3657, 33.7735)::geography),
  ('eater_jordan', '789 Northside Dr NW', 'Atlanta', 'GA', '30318',
   ST_MakePoint(-84.4112, 33.7815)::geography)
ON CONFLICT (user_id) DO NOTHING;

-- ══════════════════════════════════════════════════════════════════════════════
-- DISHES
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO dishes (cook_id, name, description, sort_order) VALUES
  ('cook_aisha', 'Doro Wat', 'Slow-simmered Ethiopian chicken stew with berbere spice and hard-boiled eggs, served with injera.', 1),
  ('cook_aisha', 'Misir Wat', 'Red lentil stew seasoned with berbere, turmeric, and aromatics. Vegan.', 2),
  ('cook_aisha', 'Kitfo', 'Ethiopian beef tartare seasoned with mitmita and niter kibbeh. Served with gomen and ayib.', 3),
  ('cook_aisha', 'Injera Platter', 'Assorted veggie and meat dishes served on fresh sourdough injera.', 4),
  ('cook_marcus', 'Smoked Brisket Plate', '14-hour oak-smoked brisket with mac & cheese, collard greens, and cornbread.', 1),
  ('cook_marcus', 'Shrimp & Grits', 'Creamy stone-ground grits with sautéed Gulf shrimp, andouille sausage, and gravy.', 2),
  ('cook_marcus', 'Scratch Biscuits & Gravy', 'Buttermilk biscuits from scratch with pork sausage gravy.', 3);

-- ══════════════════════════════════════════════════════════════════════════════
-- AVAILABILITY (Aisha: weekends + evenings, Marcus: Fri-Sun)
-- day_of_week: 0=Sun, 1=Mon, ..., 6=Sat
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO cook_availability (cook_id, day_of_week, start_hour, end_hour) VALUES
  -- Aisha: weekday evenings (Mon-Fri 17-21), all day weekends (Sat-Sun 10-21)
  ('cook_aisha', 1, 17, 21), ('cook_aisha', 2, 17, 21), ('cook_aisha', 3, 17, 21),
  ('cook_aisha', 4, 17, 21), ('cook_aisha', 5, 17, 21),
  ('cook_aisha', 0, 10, 21), ('cook_aisha', 6, 10, 21),
  -- Marcus: Fri evening, Sat-Sun all day
  ('cook_marcus', 5, 16, 21),
  ('cook_marcus', 6, 10, 21), ('cook_marcus', 0, 10, 21);

-- ══════════════════════════════════════════════════════════════════════════════
-- PANTRY (Sarah has a well-stocked kitchen)
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO pantry_items (user_id, name, category, item_type) VALUES
  ('eater_sarah', 'Chicken thighs', 'protein', 'fresh'),
  ('eater_sarah', 'Ground beef', 'protein', 'fresh'),
  ('eater_sarah', 'Eggs', 'protein', 'fresh'),
  ('eater_sarah', 'Rice', 'grains', 'staple'),
  ('eater_sarah', 'All-purpose flour', 'grains', 'staple'),
  ('eater_sarah', 'Olive oil', 'oils', 'staple'),
  ('eater_sarah', 'Butter', 'dairy', 'fresh'),
  ('eater_sarah', 'Onions', 'produce', 'staple'),
  ('eater_sarah', 'Garlic', 'produce', 'staple'),
  ('eater_sarah', 'Tomatoes', 'produce', 'fresh'),
  ('eater_sarah', 'Salt', 'spices', 'staple'),
  ('eater_sarah', 'Black pepper', 'spices', 'staple'),
  ('eater_sarah', 'Cumin', 'spices', 'staple'),
  ('eater_sarah', 'Canned tomatoes', 'canned', 'staple'),
  ('eater_sarah', 'Chicken broth', 'canned', 'staple');

-- ══════════════════════════════════════════════════════════════════════════════
-- SAMPLE BOOKING (completed, with review)
-- ══════════════════════════════════════════════════════════════════════════════

INSERT INTO bookings (
  eater_id, cook_id, status, scheduled_date, scheduled_start_time,
  estimated_duration, eater_address, eater_location,
  price_per_hour, estimated_total, actual_duration, final_total,
  platform_fee, cook_payout, eater_notes
) VALUES (
  'eater_sarah', 'cook_aisha', 'completed',
  CURRENT_DATE - INTERVAL '3 days', '18:00',
  2.0, '123 Peachtree St NE, Atlanta, GA 30309',
  ST_MakePoint(-84.3853, 33.7676)::geography,
  45.00, 99.00, 2.0, 99.00,
  9.90, 89.10,
  'Would love an Ethiopian spread! I have most basics but might need berbere spice.'
);

-- Review for the completed booking
INSERT INTO reviews (booking_id, reviewer_id, reviewee_id, role, rating, text, tags)
SELECT b.id, 'eater_sarah', 'cook_aisha', 'eater_reviewing_cook', 5,
  'Aisha was incredible! She turned my basic pantry into an amazing Ethiopian feast. The doro wat was restaurant-quality.',
  '{amazing_food,friendly,on_time}'
FROM bookings b
WHERE b.eater_id = 'eater_sarah' AND b.cook_id = 'cook_aisha'
LIMIT 1;
""";


def seed():
    init_db()
    with db_session() as session:
        # Check if already seeded
        result = session.execute(text("SELECT count(*) FROM users"))
        count = result.scalar()
        if count > 0:
            print(f"Database already has {count} users. Skipping seed.")
            print("To re-seed, run: psql $DATABASE_URL -c 'TRUNCATE users CASCADE'")
            return

        print("Seeding database...")
        session.execute(text(SEED_SQL))
        print("Done. Created:")
        for table in ['users', 'cook_profiles', 'eater_profiles', 'dishes',
                      'cook_availability', 'pantry_items', 'bookings', 'reviews']:
            r = session.execute(text(f"SELECT count(*) FROM {table}"))
            print(f"  {table}: {r.scalar()} rows")


def verify_geo():
    """Run the geo query from the spec to verify PostGIS works."""
    init_db()
    with db_session() as session:
        # Find cooks whose travel radius covers Sarah's location (Peachtree St)
        result = session.execute(text("""
            SELECT u.name, cp.cuisines, cp.price_per_hour, cp.travel_radius_miles,
                   ROUND(ST_Distance(cp.base_location, ep.location)::numeric / 1609.34, 1) AS distance_miles
            FROM cook_profiles cp
            JOIN users u ON u.id = cp.user_id
            CROSS JOIN eater_profiles ep
            WHERE ep.user_id = 'eater_sarah'
              AND ST_DWithin(cp.base_location, ep.location, cp.travel_radius_miles * 1609.34)
            ORDER BY distance_miles;
        """))
        rows = result.fetchall()
        print(f"\nGeo query: cooks within range of Sarah's location:")
        for row in rows:
            print(f"  {row.name} — {row.cuisines} — ${row.price_per_hour}/hr — {row.distance_miles} mi away")
        if not rows:
            print("  (no results — check PostGIS installation)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify-geo":
        verify_geo()
    else:
        seed()
        verify_geo()
