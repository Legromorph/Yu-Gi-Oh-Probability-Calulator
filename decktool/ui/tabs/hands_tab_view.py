from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..main_window import DeckToolMainWindow


class HandsTabView:
    """
    Pure UI/layout.
    No business logic, no data mutation.
    Exposes widgets to the controller.
    """

    def __init__(self, app: "DeckToolMainWindow") -> None:
        self.app = app

        # Always define attributes (so controller can safely access after build)
        self.filter_var = tk.StringVar(value="")

        self.hands_list: tk.Listbox | None = None

        self.btn_new: ttk.Button | None = None
        self.btn_duplicate: ttk.Button | None = None
        self.btn_delete: ttk.Button | None = None
        self.btn_save: ttk.Button | None = None

        self.must_card_var = tk.StringVar(value="")
        self.must_card_combo: ttk.Combobox | None = None
        self.must_qty_var = tk.IntVar(value=1)
        self.btn_must_add: ttk.Button | None = None
        self.btn_must_remove: ttk.Button | None = None
        self.must_tree: ttk.Treeview | None = None

        self.or_hint_var = tk.StringVar(value="Select an ideal hand first.")
        self.btn_group_add: ttk.Button | None = None
        self.btn_group_remove: ttk.Button | None = None
        self.group_list: tk.Listbox | None = None
        self.options_list: tk.Listbox | None = None

        self.or_card_var = tk.StringVar(value="")
        self.or_card_combo: ttk.Combobox | None = None
        self.or_qty_var = tk.IntVar(value=1)
        self.btn_opt_add: ttk.Button | None = None
        self.btn_opt_remove: ttk.Button | None = None

        self.editor_frame: ttk.LabelFrame | None = None

    def build(self, parent: ttk.Frame) -> None:
        root = ttk.Frame(parent, padding=12)
        root.pack(fill="both", expand=True)

        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root)
        right = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right.grid(row=0, column=1, sticky="nsew")

        # Left column: list + editor
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)
        left.columnconfigure(0, weight=1)

        # =========================
        # Ideal hands (left top)
        # =========================
        left_card = ttk.LabelFrame(left, text="Ideal hands", padding=14, style="Card.TLabelframe")
        left_card.grid(row=0, column=0, sticky="nsew")

        # Row 1: Search (full width)
        search_row = ttk.Frame(left_card, style="Card.TFrame")
        search_row.pack(fill="x", pady=(0, 8))
        search_row.columnconfigure(1, weight=1)

        ttk.Label(search_row, text="Search", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(search_row, textvariable=self.filter_var)
        ent.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # Row 2: Buttons (under search)
        btn_row = ttk.Frame(left_card, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(0, 10))

        self.btn_new = ttk.Button(btn_row, text="New", style="SmallPrimary.TButton")
        self.btn_new.pack(side="left")

        self.btn_duplicate = ttk.Button(btn_row, text="Duplicate", style="Small.TButton")
        self.btn_duplicate.pack(side="left", padx=(8, 0))

        self.btn_delete = ttk.Button(btn_row, text="Delete", style="SmallDanger.TButton")
        self.btn_delete.pack(side="right")

        # Listbox
        list_wrap = ttk.Frame(left_card, style="Card.TFrame")
        list_wrap.pack(fill="both", expand=True)

        self.hands_list = tk.Listbox(
            list_wrap,
            bd=0,
            highlightthickness=0,
            exportselection=False,
        )

        ysb = ttk.Scrollbar(list_wrap, orient="vertical", command=self.hands_list.yview)
        self.hands_list.configure(yscrollcommand=ysb.set)

        self.hands_list.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")


        # =========================
        # Editor (left bottom)
        # =========================
        self.editor_frame = ttk.LabelFrame(left, text="Editor", padding=14, style="Card.TLabelframe")
        self.editor_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.editor_frame.columnconfigure(0, weight=1)

        row1 = ttk.Frame(self.editor_frame, style="Card.TFrame")
        row1.grid(row=0, column=0, sticky="ew")
        row1.columnconfigure(1, weight=1)

        ttk.Label(row1, text="Name", style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        ttk.Entry(row1, textvariable=self.app.hand_name_var).grid(
            row=0, column=1, sticky="ew", padx=(10, 0)
        )

        row2 = ttk.Frame(self.editor_frame, style="Card.TFrame")
        row2.grid(row=1, column=0, sticky="w", pady=(12, 0))

        ttk.Label(row2, text="Base score", style="Muted.TLabel").pack(side="left")

        ttk.Spinbox(
            row2,
            from_=0,
            to=10,
            textvariable=self.app.hand_score_var,
            width=8,
        ).pack(side="left", padx=(8, 16))

        self.btn_save = ttk.Button(row2, text="Save", style="SmallPrimary.TButton")
        self.btn_save.pack(side="left")

        # --- Row 2: Base score + Save ---
        row2 = ttk.Frame(self.editor_frame, style="Card.TFrame")
        row2.grid(row=1, column=0, sticky="w", pady=(12, 0))

        ttk.Label(row2, text="Base score", style="Muted.TLabel").pack(side="left")

        ttk.Spinbox(
            row2,
            from_=0,
            to=10,
            textvariable=self.app.hand_score_var,
            width=8,
        ).pack(side="left", padx=(8, 16))

        self.btn_save = ttk.Button(row2, text="Save", style="SmallPrimary.TButton")
        self.btn_save.pack(side="left")

        # =========================
        # Right column: Must + OR horizontally
        # =========================
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(0, weight=1)

        must_box = ttk.LabelFrame(right, text="Must cards (AND)", padding=14, style="Card.TLabelframe")
        or_box = ttk.LabelFrame(right, text="OR groups (simple)", padding=14, style="Card.TLabelframe")
        must_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        or_box.grid(row=0, column=1, sticky="nsew")

        # =========================
        # MUST
        # =========================
        must_box.columnconfigure(0, weight=1)
        must_box.rowconfigure(0, weight=1)  # tree area can take space
        must_box.rowconfigure(1, weight=0)  # controls stay compact

        # --- Tree wrapper (TOP) ---
        must_tree_wrap = ttk.Frame(must_box, style="Card.TFrame")
        must_tree_wrap.grid(row=0, column=0, sticky="nsew")
        must_tree_wrap.columnconfigure(0, weight=1)
        must_tree_wrap.rowconfigure(0, weight=1)

        # Treeview WITHOUT scrollbar
        self.must_tree = ttk.Treeview(
            must_tree_wrap,
            columns=("card", "qty"),
            show="headings",
            height=10,  # adjust as you like; no scrollbar
        )

        self.must_tree.heading("card", text="Card")
        self.must_tree.heading("qty", text="Qty")
        self.must_tree.column("card", width=240, anchor="w")
        self.must_tree.column("qty", width=70, anchor="center")

        # Let it fill available area (still no scrollbar)
        self.must_tree.grid(row=0, column=0, sticky="nsew")

        # --- Controls (BOTTOM) ---
        must_controls = ttk.Frame(must_box, style="Card.TFrame")
        must_controls.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        must_controls.columnconfigure(0, weight=1)

        ttk.Label(must_controls, text="Card", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.must_card_combo = ttk.Combobox(must_controls, textvariable=self.must_card_var, state="readonly")
        self.must_card_combo.grid(row=1, column=0, sticky="ew", pady=(4, 10))

        row = ttk.Frame(must_controls, style="Card.TFrame")
        row.grid(row=2, column=0, sticky="ew")

        ttk.Label(row, text="Qty", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=1, to=4, textvariable=self.must_qty_var, width=6).pack(side="left", padx=(8, 16))

        self.btn_must_add = ttk.Button(row, text="Add", style="SmallPrimary.TButton")
        self.btn_must_add.pack(side="left")

        self.btn_must_remove = ttk.Button(row, text="Remove", style="Small.TButton")
        self.btn_must_remove.pack(side="left", padx=(8, 0))

        # =========================
        # OR
        # =========================
        or_box.columnconfigure(0, weight=1)

        # Give ALL remaining vertical space to the scroll area (pane)
        or_box.rowconfigure(0, weight=0)   # hint
        or_box.rowconfigure(1, weight=1)   # pane (must expand)
        or_box.rowconfigure(2, weight=0)   # group buttons
        or_box.rowconfigure(3, weight=0)

        hint = ttk.Frame(or_box, style="Card.TFrame")
        hint.grid(row=0, column=0, sticky="ew")
        ttk.Label(hint, textvariable=self.or_hint_var, style="Muted.TLabel").pack(anchor="w")

        or_pane = ttk.Panedwindow(or_box, orient="horizontal")
        or_pane.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        or_pane.configure(height=320)

        or_left = ttk.Frame(or_pane, style="Card.TFrame")
        or_right = ttk.Frame(or_pane, style="Card.TFrame")
        or_pane.add(or_left, weight=1)
        or_pane.add(or_right, weight=2)

        # Make inner frames expand properly
        or_left.pack_propagate(False)
        or_right.pack_propagate(False)

        ttk.Label(or_left, text="Groups", style="Muted.TLabel").pack(anchor="w")
        self.group_list = tk.Listbox(or_left, bd=0, highlightthickness=0, exportselection=False)
        self.group_list.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(or_right, text="Options (OR)", style="Muted.TLabel").pack(anchor="w")
        self.options_list = tk.Listbox(or_right, bd=0, highlightthickness=0, exportselection=False)
        self.options_list.pack(fill="both", expand=True, pady=(8, 0))

        group_actions = ttk.Frame(or_box, style="Card.TFrame")
        group_actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.btn_group_add = ttk.Button(group_actions, text="Add group", style="Small.TButton")
        self.btn_group_add.pack(side="left")

        self.btn_group_remove = ttk.Button(group_actions, text="Remove group", style="SmallDanger.TButton")
        self.btn_group_remove.pack(side="left", padx=(8, 0))

        opt_controls = ttk.Frame(or_box, style="Card.TFrame")
        opt_controls.grid(row=3, column=0, sticky="ew")
        opt_controls.columnconfigure(0, weight=1)

        ttk.Label(opt_controls, text="Card", style="Muted.TLabel").grid(row=0, column=0, sticky="w")

        self.or_card_combo = ttk.Combobox(opt_controls, textvariable=self.or_card_var, state="readonly")
        self.or_card_combo.grid(row=1, column=0, sticky="ew", pady=(4, 10))

        opt_row = ttk.Frame(opt_controls, style="Card.TFrame")
        opt_row.grid(row=2, column=0, sticky="ew")

        ttk.Label(opt_row, text="Qty", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(
            opt_row,
            from_=1,
            to=4,
            textvariable=self.or_qty_var,
            width=6,
        ).pack(side="left", padx=(8, 16))

        self.btn_opt_add = ttk.Button(opt_row, text="Add", style="SmallPrimary.TButton")
        self.btn_opt_add.pack(side="left")

        self.btn_opt_remove = ttk.Button(opt_row, text="Remove", style="SmallDanger.TButton")
        self.btn_opt_remove.pack(side="left", padx=(8, 0))
