-- 010_ethio_marketplace.sql — Ethio-Cook (Addis) food-ordering marketplace.
--
-- Kitchens (a cook's storefront, slug id), their menus, and food orders (delivery/pickup, paid via
-- telebirr / Chapa / CBE Birr / cash-on-delivery). Separate from the beam broadcast and the US
-- in-home booking flows. Amounts are ETB major units. Seeds the 5 demo Addis kitchens so /et/kitchens
-- returns content immediately; real cook-created kitchens add to this.
--
-- Idempotent DDL (IF NOT EXISTS) + idempotent seed (ON CONFLICT DO NOTHING). Reuses
-- update_updated_at() from 001_initial.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS ethio_kitchens (
  id          TEXT PRIMARY KEY,                                   -- url slug, e.g. 'tsehay'
  cook_id     TEXT REFERENCES users(id) ON DELETE SET NULL,       -- owner; null for seed demo
  name        TEXT NOT NULL,
  initial     TEXT,
  tier        TEXT NOT NULL DEFAULT 'bronze' CHECK (tier IN ('gold','silver','bronze')),
  score       INTEGER NOT NULL DEFAULT 0,
  rating      NUMERIC(2,1),
  hood        TEXT,
  city        TEXT NOT NULL DEFAULT 'Addis Ababa',
  base_price  NUMERIC(8,2),
  mode        TEXT NOT NULL DEFAULT 'delivery' CHECK (mode IN ('delivery','pickup')),
  is_open     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ethio_menu_items (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kitchen_id  TEXT NOT NULL REFERENCES ethio_kitchens(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  price       NUMERIC(8,2) NOT NULL,
  available   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ethio_orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  eater_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kitchen_id      TEXT NOT NULL REFERENCES ethio_kitchens(id) ON DELETE CASCADE,
  mode            TEXT NOT NULL DEFAULT 'delivery' CHECK (mode IN ('delivery','pickup')),
  payment_method  TEXT NOT NULL CHECK (payment_method IN ('cod','telebirr','chapa','cbe')),
  payment_status  TEXT NOT NULL DEFAULT 'pending'
                    CHECK (payment_status IN ('pending','cod_pending','paid','failed')),
  status          TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new','preparing','ready','delivered','cancelled')),
  total           NUMERIC(8,2) NOT NULL,
  address         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ethio_order_items (
  id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id  UUID NOT NULL REFERENCES ethio_orders(id) ON DELETE CASCADE,
  name      TEXT NOT NULL,
  price     NUMERIC(8,2) NOT NULL,
  qty       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_ethio_kitchens_open ON ethio_kitchens (is_open, lower(city));
CREATE INDEX IF NOT EXISTS idx_ethio_kitchens_cook ON ethio_kitchens (cook_id);
CREATE INDEX IF NOT EXISTS idx_ethio_menu_kitchen  ON ethio_menu_items (kitchen_id);
CREATE INDEX IF NOT EXISTS idx_ethio_orders_eater  ON ethio_orders (eater_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ethio_orders_kitchen ON ethio_orders (kitchen_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ethio_order_items_order ON ethio_order_items (order_id);

DROP TRIGGER IF EXISTS trg_ethio_kitchens_updated_at ON ethio_kitchens;
CREATE TRIGGER trg_ethio_kitchens_updated_at BEFORE UPDATE ON ethio_kitchens
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
DROP TRIGGER IF EXISTS trg_ethio_orders_updated_at ON ethio_orders;
CREATE TRIGGER trg_ethio_orders_updated_at BEFORE UPDATE ON ethio_orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Seed: the 5 demo Addis kitchens (idempotent) ──────────────────────────────
INSERT INTO ethio_kitchens (id, name, initial, tier, score, rating, hood, base_price, mode) VALUES
  ('tsehay', 'Tsehay''s Kitchen',   'T', 'gold',   94, 4.9, 'Bole',      320, 'delivery'),
  ('marta',  'Marta''s Mesob',      'M', 'gold',   91, 4.8, 'Kazanchis', 380, 'delivery'),
  ('selam',  'Selam Home Foods',    'S', 'silver', 86, 4.7, 'Piassa',    180, 'pickup'),
  ('dawit',  'Dawit''s Tibs House', 'D', 'gold',   90, 4.8, 'Gerji',     450, 'delivery'),
  ('hiwot',  'Hiwot Beyaynetu',     'H', 'silver', 84, 4.9, 'CMC',       220, 'delivery')
ON CONFLICT (id) DO NOTHING;

INSERT INTO ethio_menu_items (kitchen_id, name, price, available) VALUES
  ('tsehay', 'Doro wot', 320, TRUE), ('tsehay', 'Beyaynetu', 220, TRUE), ('tsehay', 'Tibs', 450, TRUE), ('tsehay', 'Kitfo', 400, FALSE),
  ('marta', 'Kitfo', 400, TRUE), ('marta', 'Gomen', 180, TRUE), ('marta', 'Key wot', 360, TRUE),
  ('selam', 'Shiro', 150, TRUE), ('selam', 'Misir wot', 170, TRUE), ('selam', 'Firfir', 160, TRUE),
  ('dawit', 'Tibs', 450, TRUE), ('dawit', 'Kitfo', 420, TRUE),
  ('hiwot', 'Beyaynetu', 220, TRUE), ('hiwot', 'Shiro', 150, TRUE), ('hiwot', 'Gomen', 180, TRUE)
ON CONFLICT DO NOTHING;

COMMIT;
