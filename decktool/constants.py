# region Handtrap constants
# List of supported handtraps in the UI and simulation.
HANDTRAPS = [
    "nibiru", "ash", "imperm", "veiler", "belle",
    "mourner", "impulse", "purge", "fuwa", "purulia"
]

# Handtraps that are treated as draw-type effects.
DRAW_HANDTRAPS = {"fuwa", "purulia"}

# Default handtrap modes (name -> "impact" | "draws").
HANDTRAP_DEFS = {t: ("draws" if t in DRAW_HANDTRAPS else "impact") for t in HANDTRAPS}

# Human-readable labels for impact levels.
IMPACT_LABELS = {
    0: "0 - no effect",
    1: "1 - slightly worse",
    2: "2 - noticeably worse",
    3: "3 - almost stopped",
    4: "4 - stopped",
}
# endregion

# region Card tag constants
# Default tag keys + labels used in the Card Settings dialog.
CARD_TAGS = [
    ("engine", "Engine"),
    ("engine-req", "Engine requirement"),
    ("endboard", "Endboard piece"),
    ("extender", "Extender"),
    ("non-engine", "Non-engine"),
]
# endregion
