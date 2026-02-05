# region Handtrap constants
# List of supported handtraps in the UI and simulation.
HANDTRAPS = [
    "nibiru", "ash", "imperm", "veiler", "belle",
    "mourner", "impulse", "purge", "fuwa", "purulia"
]

# Handtraps that are treated as draw-type effects.
DRAW_HANDTRAPS = {"fuwa", "purulia"}

# Human-readable labels for impact levels.
IMPACT_LABELS = {
    0: "0 - no effect",
    1: "1 - slightly worse",
    2: "2 - noticeably worse",
    3: "3 - almost stopped",
    4: "4 - stopped",
}
# endregion
