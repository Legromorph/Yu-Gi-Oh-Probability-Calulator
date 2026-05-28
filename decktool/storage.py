from __future__ import annotations

# region Imports
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .models import IdealHand, DeckVariant, CardMeta, DrawEffect, ProsperityEffect
# endregion


# region Data container
@dataclass
class ProjectData:
    deck_variants: List[DeckVariant]
    active_deck_id: str
    card_meta: Dict[str, CardMeta]
    ideal_hands: Dict[str, IdealHand]
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]]
    handtrap_defs: Dict[str, str]
    id_counter: int
    optimize_state: Dict[str, Any]
    version: int = 6
# endregion


# region JSON serialization helpers
def project_to_dict(
    deck_variants: List[DeckVariant],
    active_deck_id: str,
    card_meta: Dict[str, CardMeta],
    ideal_hands: Dict[str, IdealHand],
    handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]],
    handtrap_defs: Dict[str, str],
    id_counter: int,
    optimize_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Serialize the entire project state to a dict (legacy JSON)."""
    return {
        "version": 6,
        "decklists": [dv.to_dict() for dv in deck_variants],
        "active_deck_id": active_deck_id,
        "card_meta": {k: v.to_dict() for k, v in (card_meta or {}).items()},
        "ideal_hands": [h.to_dict() for h in ideal_hands.values()],
        "handtrap_effects": handtrap_effects,
        "handtrap_defs": handtrap_defs,
        "id_counter": id_counter,
        "optimize_state": optimize_state or {},
    }


def project_from_dict(
    data: Dict[str, Any],
) -> ProjectData:
    """Deserialize a project dict into runtime objects."""
    deck_variants: List[DeckVariant] = []
    active_deck_id = ""

    if "decklists" in data:
        for dv in data.get("decklists", []) or []:
            deck_variants.append(DeckVariant.from_dict(dv))
        active_deck_id = str(data.get("active_deck_id", "") or "")
    else:
        # legacy format: single decklist
        deck_variants.append(
            DeckVariant(id="D01", name="Variant 1", decklist=dict(data.get("decklist", {}) or {}))
        )
        active_deck_id = "D01"

    if not deck_variants:
        deck_variants.append(DeckVariant(id="D01", name="Variant 1", decklist={}))
        active_deck_id = "D01"

    card_meta: Dict[str, CardMeta] = {}
    for cname, meta in (data.get("card_meta", {}) or {}).items():
        try:
            card_meta[str(cname)] = CardMeta.from_dict(meta or {})
        except Exception:
            continue

    ideal_hands: Dict[str, IdealHand] = {}
    for hd in data.get("ideal_hands", []):
        hand = IdealHand.from_dict(hd)
        ideal_hands[hand.id] = hand

    handtrap_effects = data.get("handtrap_effects", {}) or {}
    handtrap_defs = data.get("handtrap_defs", {}) or {}
    id_counter = int(data.get("id_counter", 1))
    optimize_state = data.get("optimize_state", {}) or {}

    return ProjectData(
        deck_variants=deck_variants,
        active_deck_id=active_deck_id,
        card_meta=card_meta,
        ideal_hands=ideal_hands,
        handtrap_effects=handtrap_effects,
        handtrap_defs=handtrap_defs,
        id_counter=id_counter,
        optimize_state=optimize_state,
        version=int(data.get("version", 6) or 6),
    )
# endregion


# region SQLite storage
_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deck_variants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sort_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS deck_cards (
    variant_id TEXT NOT NULL,
    card TEXT NOT NULL,
    qty INTEGER NOT NULL,
    bench INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (variant_id, card, bench)
);

CREATE TABLE IF NOT EXISTS card_meta (
    card TEXT PRIMARY KEY,
    tags_json TEXT NOT NULL,
    draw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ideal_hands (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_score INTEGER NOT NULL,
    handtrap_only INTEGER NOT NULL DEFAULT 0,
    must_json TEXT NOT NULL,
    or_groups_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handtrap_defs (
    name TEXT PRIMARY KEY,
    mode TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handtrap_effects (
    hand_id TEXT NOT NULL,
    trap TEXT NOT NULL,
    mode TEXT NOT NULL,
    value INTEGER NOT NULL,
    PRIMARY KEY (hand_id, trap)
);
"""


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_DB_SCHEMA)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_loads(text: str) -> Any:
    if not text:
        return None
    return json.loads(text)


def _deck_variants_from_db(conn: sqlite3.Connection) -> Tuple[List[DeckVariant], str]:
    cur = conn.execute("SELECT id, name FROM deck_variants ORDER BY sort_index ASC")
    variants = []
    for row in cur.fetchall():
        variants.append(DeckVariant(id=str(row[0]), name=str(row[1]), decklist={}, bench={}))
    return variants, ""


def _load_project_db(path: str) -> ProjectData:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_db(conn)

        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
        deck_variants: List[DeckVariant] = []
        cur = conn.execute("SELECT id, name, sort_index FROM deck_variants ORDER BY sort_index ASC")
        for row in cur.fetchall():
            deck_variants.append(
                DeckVariant(id=str(row["id"]), name=str(row["name"]), decklist={}, bench={})
            )

        # Deck cards
        card_rows = conn.execute(
            "SELECT variant_id, card, qty, bench FROM deck_cards ORDER BY variant_id, card"
        ).fetchall()
        deck_map = {dv.id: dv for dv in deck_variants}
        for row in card_rows:
            vid = str(row["variant_id"])
            dv = deck_map.get(vid)
            if not dv:
                continue
            card = str(row["card"])
            qty = int(row["qty"])
            if int(row["bench"]) == 1:
                dv.bench[card] = qty
            else:
                dv.decklist[card] = qty

        # Card meta
        card_meta: Dict[str, CardMeta] = {}
        for row in conn.execute("SELECT card, tags_json, draw_json FROM card_meta"):
            card = str(row["card"])
            tags = _json_loads(row["tags_json"]) or []
            draw_json = _json_loads(row["draw_json"]) or {}
            draw_effect = None
            prosperity_effect = None
            max_copies = 0
            if draw_json:
                if any(k in draw_json for k in ("draw_effect", "prosperity_effect", "max_copies", "required_cards")):
                    draw_blob = draw_json.get("draw_effect") or {}
                    prosp_blob = draw_json.get("prosperity_effect") or {}
                    max_copies = int(draw_json.get("max_copies", 0) or 0)
                    req_cards = [str(c) for c in (draw_json.get("required_cards", []) or [])]
                    if draw_blob:
                        try:
                            draw_effect = DrawEffect.from_dict(draw_blob)
                        except Exception:
                            draw_effect = None
                    if prosp_blob:
                        try:
                            prosperity_effect = ProsperityEffect.from_dict(prosp_blob)
                        except Exception:
                            prosperity_effect = None
                else:
                    # Legacy payload: flat draw effect only.
                    req_cards = []
                    try:
                        draw_effect = DrawEffect.from_dict(draw_json)
                    except Exception:
                        draw_effect = None
            else:
                req_cards = []
            card_meta[card] = CardMeta(
                tags=list(tags),
                draw_effect=draw_effect,
                prosperity_effect=prosperity_effect,
                max_copies=max_copies,
                required_cards=req_cards,
            )

        # Ideal hands
        ideal_hands: Dict[str, IdealHand] = {}
        for row in conn.execute("SELECT * FROM ideal_hands"):
            must = _json_loads(row["must_json"]) or {}
            or_groups = _json_loads(row["or_groups_json"]) or []
            hand = IdealHand(
                id=str(row["id"]),
                name=str(row["name"]),
                base_score=int(row["base_score"]),
                must={str(k): int(v) for k, v in (must or {}).items()},
                or_groups=or_groups,
                handtrap_only=bool(int(row["handtrap_only"]))
            )
            ideal_hands[hand.id] = hand

        # Handtrap defs
        handtrap_defs = {str(r["name"]): str(r["mode"]) for r in conn.execute("SELECT * FROM handtrap_defs")}

        # Handtrap effects
        handtrap_effects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in conn.execute("SELECT * FROM handtrap_effects"):
            hid = str(row["hand_id"])
            trap = str(row["trap"])
            mode = str(row["mode"])
            value = int(row["value"])
            handtrap_effects.setdefault(hid, {})[trap] = {"mode": mode, "value": value}

        active_deck_id = str(meta.get("active_deck_id", "") or "")
        id_counter = int(meta.get("id_counter", 1))
        optimize_state = _json_loads(meta.get("optimize_state", "")) or {}
        version = int(meta.get("version", 1))

        return ProjectData(
            deck_variants=deck_variants,
            active_deck_id=active_deck_id,
            card_meta=card_meta,
            ideal_hands=ideal_hands,
            handtrap_effects=handtrap_effects,
            handtrap_defs=handtrap_defs,
            id_counter=id_counter,
            optimize_state=optimize_state,
            version=version,
        )


def _save_project_db(path: str, data: ProjectData) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with sqlite3.connect(path) as conn:
        _ensure_db(conn)
        with conn:
            conn.execute("DELETE FROM deck_cards")
            conn.execute("DELETE FROM deck_variants")
            conn.execute("DELETE FROM card_meta")
            conn.execute("DELETE FROM ideal_hands")
            conn.execute("DELETE FROM handtrap_defs")
            conn.execute("DELETE FROM handtrap_effects")
            conn.execute("DELETE FROM meta")

            for idx, dv in enumerate(data.deck_variants):
                conn.execute(
                    "INSERT INTO deck_variants (id, name, sort_index) VALUES (?, ?, ?)",
                    (dv.id, dv.name, idx),
                )
                for card, qty in (dv.decklist or {}).items():
                    conn.execute(
                        "INSERT INTO deck_cards (variant_id, card, qty, bench) VALUES (?, ?, ?, 0)",
                        (dv.id, card, int(qty)),
                    )
                for card, qty in (dv.bench or {}).items():
                    conn.execute(
                        "INSERT INTO deck_cards (variant_id, card, qty, bench) VALUES (?, ?, ?, 1)",
                        (dv.id, card, int(qty)),
                    )

            for card, meta in (data.card_meta or {}).items():
                tags_json = _json_dumps(meta.tags or [])
                effect_payload: Dict[str, Any] = {}
                if meta.draw_effect:
                    effect_payload["draw_effect"] = meta.draw_effect.to_dict()
                if getattr(meta, "prosperity_effect", None):
                    effect_payload["prosperity_effect"] = meta.prosperity_effect.to_dict()
                max_copies = int(getattr(meta, "max_copies", 0) or 0)
                if max_copies > 0:
                    effect_payload["max_copies"] = max_copies
                req_cards = [str(c) for c in (getattr(meta, "required_cards", []) or []) if str(c).strip()]
                if req_cards:
                    effect_payload["required_cards"] = req_cards
                draw_json = _json_dumps(effect_payload)
                conn.execute(
                    "INSERT INTO card_meta (card, tags_json, draw_json) VALUES (?, ?, ?)",
                    (card, tags_json, draw_json),
                )

            for hand in data.ideal_hands.values():
                conn.execute(
                    "INSERT INTO ideal_hands (id, name, base_score, handtrap_only, must_json, or_groups_json)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        hand.id,
                        hand.name,
                        int(hand.base_score),
                        1 if hand.handtrap_only else 0,
                        _json_dumps(hand.must or {}),
                        _json_dumps(hand.or_groups or []),
                    ),
                )

            for name, mode in (data.handtrap_defs or {}).items():
                conn.execute(
                    "INSERT INTO handtrap_defs (name, mode) VALUES (?, ?)",
                    (name, mode),
                )

            for hid, effects in (data.handtrap_effects or {}).items():
                for trap, eff in (effects or {}).items():
                    conn.execute(
                        "INSERT INTO handtrap_effects (hand_id, trap, mode, value) VALUES (?, ?, ?, ?)",
                        (
                            hid,
                            trap,
                            str(eff.get("mode", "impact")),
                            int(eff.get("value", 0)),
                        ),
                    )

            meta_rows = {
                "version": str(int(data.version or 1)),
                "active_deck_id": str(data.active_deck_id or ""),
                "id_counter": str(int(data.id_counter or 1)),
                "optimize_state": _json_dumps(data.optimize_state or {}),
            }
            for key, value in meta_rows.items():
                conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (key, value))


def _save_optimize_state_db(path: str, optimize_state: Dict[str, Any]) -> None:
    with sqlite3.connect(path) as conn:
        _ensure_db(conn)
        with conn:
            conn.execute("DELETE FROM meta WHERE key = 'optimize_state'")
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                ("optimize_state", _json_dumps(optimize_state or {})),
            )
# endregion


# region File detection + unified API
_SQLITE_HEADER = b"SQLite format 3\x00"


def _is_sqlite_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        return header.startswith(_SQLITE_HEADER)
    except Exception:
        return False


def load_project(path: str) -> ProjectData:
    """Load a project file (JSON or SQLite)."""
    if _is_sqlite_file(path) or path.lower().endswith((".deckdb", ".db")):
        return _load_project_db(path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return project_from_dict(data)


def save_project(path: str, data: ProjectData) -> None:
    """Save a project file (JSON or SQLite, based on extension)."""
    if path.lower().endswith(".json"):
        payload = project_to_dict(
            data.deck_variants,
            data.active_deck_id,
            data.card_meta,
            data.ideal_hands,
            data.handtrap_effects,
            data.handtrap_defs,
            data.id_counter,
            data.optimize_state,
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return

    _save_project_db(path, data)


def save_optimize_state(path: str, optimize_state: Dict[str, Any]) -> None:
    """Save only optimize_state if possible; falls back to full save for JSON."""
    if _is_sqlite_file(path) or path.lower().endswith((".deckdb", ".db")):
        _save_optimize_state_db(path, optimize_state)
        return

    # JSON fallback: load -> update -> save
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["optimize_state"] = optimize_state or {}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
# endregion
