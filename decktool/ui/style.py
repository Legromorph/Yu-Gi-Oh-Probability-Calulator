from __future__ import annotations

# region Imports
import tkinter as tk
from tkinter import ttk
# endregion


# region App styling
def apply_app_style(root: tk.Tk) -> None:
    """Configure theme, colors, and widget styles for the app."""
    style = ttk.Style(root)

    if "clam" in style.theme_names():
        style.theme_use("clam")

    # ---- Palette ----
    BG = "#F3F6FB"
    CARD = "#FFFFFF"
    BORDER = "#D9E1EE"
    TEXT = "#0F172A"
    MUTED = "#64748B"
    ACCENT = "#2563EB"
    SELECT = "#DCEBFF"

    root.configure(bg=BG)

    # Fonts
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*Dialog.msg.font", ("Segoe UI", 10))
    root.option_add("*Menu*Font", ("Segoe UI", 10))

    # Base
    style.configure(".", background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 16, "bold"))
    style.configure("Subheader.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))

    # Card-like frames
    style.configure(
        "Card.TLabelframe",
        background=CARD,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=CARD,
        foreground=TEXT,
        font=("Segoe UI", 10, "bold"),
    )
    style.configure("Card.TFrame", background=CARD)

    # Inputs
    style.configure("TEntry", padding=(10, 7), relief="solid", borderwidth=1)
    style.configure("TCombobox", padding=(10, 7))
    style.configure("TSpinbox", padding=(10, 7))

    # Notebook
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=(12, 8),
        background=BG,
        foreground=MUTED,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", CARD)],
        foreground=[("selected", TEXT)],
        padding=[("selected", (16, 12)), ("!selected", (12, 8))],
    )

    # Tables
    style.configure(
        "Treeview",
        background=CARD,
        fieldbackground=CARD,
        foreground=TEXT,
        borderwidth=1,
        relief="solid",
        rowheight=28,
    )
    style.configure(
        "Treeview.Heading",
        background="#EEF2FF",
        foreground=TEXT,
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        padding=(10, 7),
    )
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])

    style.configure("TProgressbar", troughcolor="#E5E7EB", bordercolor=BORDER, background=ACCENT)

    # ---- Buttons: ONE source of truth ----
    _install_button_styles(style)


def _install_button_styles(style: ttk.Style) -> None:
    """Define button styles once so all tabs stay consistent."""
    base_font = ("TkDefaultFont", 10)
    small_font = ("TkDefaultFont", 9)

    # Normal button
    style.configure("TButton", padding=(10, 7), font=base_font)

    # Primary
    style.configure("Primary.TButton", padding=(12, 7), font=base_font)
    style.map(
        "Primary.TButton",
        foreground=[("disabled", "#9aa4b2"), ("!disabled", "white")],
        background=[
            ("pressed", "#1E40AF"),
            ("active", "#1D4ED8"),
            ("!disabled", "#2563EB"),
        ],
        bordercolor=[("!disabled", "#2563EB")],
        focuscolor=[("!disabled", "#2563EB")],
        lightcolor=[("!disabled", "#2563EB")],
        darkcolor=[("!disabled", "#2563EB")],
    )

    # Danger
    style.configure("Danger.TButton", padding=(12, 7), font=base_font)
    style.map(
        "Danger.TButton",
        foreground=[("disabled", "#9aa4b2"), ("!disabled", "white")],
        background=[
            ("pressed", "#991B1B"),
            ("active", "#B91C1C"),
            ("!disabled", "#DC2626"),
        ],
        bordercolor=[("!disabled", "#DC2626")],
        focuscolor=[("!disabled", "#DC2626")],
        lightcolor=[("!disabled", "#DC2626")],
        darkcolor=[("!disabled", "#DC2626")],
    )

    # Small variants
    style.configure("Small.TButton", padding=(8, 5), font=small_font)

    style.configure("SmallPrimary.TButton", padding=(8, 5), font=small_font)
    style.map(
        "SmallPrimary.TButton",
        foreground=style.map("Primary.TButton", "foreground"),
        background=style.map("Primary.TButton", "background"),
        bordercolor=style.map("Primary.TButton", "bordercolor"),
        focuscolor=style.map("Primary.TButton", "focuscolor"),
        lightcolor=style.map("Primary.TButton", "lightcolor"),
        darkcolor=style.map("Primary.TButton", "darkcolor"),
    )

    style.configure("SmallDanger.TButton", padding=(8, 5), font=small_font)
    style.map(
        "SmallDanger.TButton",
        foreground=style.map("Danger.TButton", "foreground"),
        background=style.map("Danger.TButton", "background"),
        bordercolor=style.map("Danger.TButton", "bordercolor"),
        focuscolor=style.map("Danger.TButton", "focuscolor"),
        lightcolor=style.map("Danger.TButton", "lightcolor"),
        darkcolor=style.map("Danger.TButton", "darkcolor"),
    )
# endregion
