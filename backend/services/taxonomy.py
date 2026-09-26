"""
Culinary skill taxonomy (server) — mirrors frontend/src/data/culinaryTaxonomy.js. The same
canonical IDs are emitted by the resume parser and required by the role scorecard, so matching is
exact graph overlap (a child node satisfies a parent). Keep this in sync with the JS copy
(single-source-of-truth via a shared JSON is a later refactor).
"""
import re

TAXONOMY_VERSION = "1.0"

# (id, label, [aliases], [parents], category)
_NODES = [
    ("knife_skills", "Knife skills", ["knife skill", "knifework", "knife work"], [], "technique"),
    ("brunoise", "Brunoise", ["fine dice"], ["knife_skills"], "technique"),
    ("julienne", "Julienne", ["matchstick"], ["knife_skills"], "technique"),
    ("dice", "Dice", ["dicing", "diced"], ["knife_skills"], "technique"),
    ("chiffonade", "Chiffonade", [], ["knife_skills"], "technique"),
    ("batonnet", "Batonnet", ["baton"], ["knife_skills"], "technique"),
    ("rock_chop", "Rock chop", ["rock chopping"], ["knife_skills"], "technique"),
    ("guillotine_cut", "Guillotine cut", ["guillotine dice", "push cut"], ["knife_skills"], "technique"),
    ("butchery", "Butchery", ["butcher", "fabrication", "breaking down", "filleting"], ["knife_skills"], "technique"),
    ("high_volume_prep", "High-volume prep", ["high volume", "batch prep", "volume prep"], ["knife_skills"], "technique"),
    ("sauteing", "Sauteing", ["saute", "sauté"], [], "technique"),
    ("grilling", "Grilling", ["grill", "broiling"], [], "technique"),
    ("braising", "Braising", ["braise"], [], "technique"),
    ("roasting", "Roasting", ["roast"], [], "technique"),
    ("sauce_making", "Sauce making", ["saucier", "mother sauces", "sauces"], [], "technique"),
    ("baking", "Baking", ["bake"], [], "technique"),
    ("pastry", "Pastry", ["patisserie", "pastries"], ["baking"], "technique"),
    ("plating", "Plating & presentation", ["plating", "presentation", "garnish"], [], "technique"),
    ("sous_vide", "Sous vide", [], [], "technique"),
    ("italian", "Italian", ["pasta", "risotto"], [], "cuisine"),
    ("mexican", "Mexican", ["tex-mex", "taqueria"], [], "cuisine"),
    ("ethiopian", "Ethiopian", ["injera", "habesha"], [], "cuisine"),
    ("french", "French", ["classical french"], [], "cuisine"),
    ("japanese", "Japanese", ["sushi", "izakaya"], [], "cuisine"),
    ("chinese", "Chinese", ["sichuan", "cantonese", "dim sum", "wok"], [], "cuisine"),
    ("indian", "Indian", ["south indian", "tandoor"], [], "cuisine"),
    ("thai", "Thai", [], [], "cuisine"),
    ("southern_us", "Southern", ["soul food", "southern"], [], "cuisine"),
    ("bbq", "BBQ", ["barbecue", "smoking", "smoked"], [], "cuisine"),
    ("mediterranean", "Mediterranean", ["levantine"], [], "cuisine"),
    ("west_african", "West African", ["jollof"], [], "cuisine"),
    ("vegan", "Vegan", ["plant-based", "plant based"], [], "cuisine"),
    ("vegetarian", "Vegetarian", [], [], "cuisine"),
    ("food_safety_cert", "Food-safety certification", [], [], "certification"),
    ("servsafe_manager", "ServSafe Manager", ["servsafe manager", "servsafe food protection manager"], ["food_safety_cert"], "certification"),
    ("servsafe_food_handler", "ServSafe Food Handler", ["servsafe food handler", "servsafe handler"], ["food_safety_cert"], "certification"),
    ("food_handler_card", "Food Handler card", ["food handler", "food handler's card", "food handlers card"], ["food_safety_cert"], "certification"),
    ("allergen_cert", "Allergen Awareness", ["allergen awareness", "allergen certification"], ["food_safety_cert"], "certification"),
    ("culinary_credential", "Culinary credential", ["culinary degree", "culinary diploma", "culinary arts"], [], "certification"),
    ("line_cook", "Line cook", ["line cook", "on the line"], [], "station"),
    ("prep_cook", "Prep cook", ["prep cook", "prep"], [], "station"),
    ("saute_station", "Sauté station", ["saute station"], [], "station"),
    ("grill_station", "Grill station", ["grill cook"], [], "station"),
    ("garde_manger", "Garde manger", ["cold station", "pantry"], [], "station"),
    ("pastry_station", "Pastry station", ["pastry chef", "pastry cook"], [], "station"),
    ("sous_chef", "Sous chef", ["sous"], [], "station"),
    ("expediter", "Expediter", ["expo", "expediting"], [], "station"),
    ("food_safety", "Food safety", ["sanitation", "safe food handling"], [], "food_safety"),
    ("haccp", "HACCP", [], ["food_safety"], "food_safety"),
    ("allergen_handling", "Allergen handling", ["allergen handling", "cross-contamination"], ["food_safety"], "food_safety"),
    ("temperature_control", "Temperature control", ["temp control", "cold chain"], ["food_safety"], "food_safety"),
]

NODES = [{"id": n[0], "label": n[1], "aliases": n[2], "parents": n[3], "category": n[4]} for n in _NODES]
BY_ID = {n["id"]: n for n in NODES}


def label_of(node_id):
    return BY_ID.get(node_id, {}).get("label", node_id)


def ancestors(node_id, seen=None):
    seen = set() if seen is None else seen
    n = BY_ID.get(node_id)
    if not n:
        return seen
    for p in n["parents"]:
        if p not in seen:
            seen.add(p)
            ancestors(p, seen)
    return seen


def satisfies(point_id, requirement_id):
    return point_id == requirement_id or requirement_id in ancestors(point_id)


_NEG = re.compile(r"\b(no|not|never|without|lack)\b")


def scan_text(text):
    """Negation-aware trie pass → [{canonical_id,label,category,evidence_span,confidence}]."""
    if not text:
        return []
    lower = " " + re.sub(r"\s+", " ", text.lower()) + " "
    hits = {}
    for n in NODES:
        terms = [n["label"].lower()] + [a.lower() for a in n["aliases"]]
        for term in terms:
            i = lower.find(" " + term + " ")
            if i == -1:
                i = lower.find(" " + term + ",")
            if i == -1:
                i = lower.find(" " + term + ".")
            if i == -1:
                continue
            before = lower[max(0, i - 14):i]
            if _NEG.search(before):
                continue
            start = lower.find(term, max(0, i))
            hits[n["id"]] = {
                "canonical_id": n["id"], "label": n["label"], "category": n["category"],
                "evidence_span": text[max(0, start - 24):start + len(term) + 24].strip(),
                "confidence": 0.95 if term == n["label"].lower() else 0.8,
            }
            break
    return list(hits.values())
