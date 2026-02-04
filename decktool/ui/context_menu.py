from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


def bind_treeview_right_click_delete(
    tree: ttk.Treeview,
    delete_cb: Callable[[], None],
    label: str = "Delete",
) -> None:
    menu = tk.Menu(tree, tearoff=False)
    menu.add_command(label=label, command=delete_cb)

    def popup(event):
        iid = tree.identify_row(event.y)
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
            menu.tk_popup(event.x_root, event.y_root)

    tree.bind("<Button-3>", popup)  # Windows/Linux
    tree.bind("<Button-2>", popup)  # macOS (some configs)


def bind_listbox_right_click_delete(
    lb: tk.Listbox,
    delete_cb: Callable[[], None],
    label: str = "Delete",
) -> None:
    menu = tk.Menu(lb, tearoff=False)
    menu.add_command(label=label, command=delete_cb)

    def popup(event):
        idx = lb.nearest(event.y)
        if idx >= 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.activate(idx)
            menu.tk_popup(event.x_root, event.y_root)

    lb.bind("<Button-3>", popup)
    lb.bind("<Button-2>", popup)
