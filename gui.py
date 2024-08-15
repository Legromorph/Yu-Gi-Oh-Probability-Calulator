import tkinter as tk
from tkinter import ttk, messagebox
from deck_manager import DeckManager
from probability_calculator import ProbabilityCalculator

class YugiohProbabilityCalculator:
    def __init__(self, master):
        self.master = master
        master.title("Yu-Gi-Oh! Wahrscheinlichkeitsrechner")

        self.deck_manager = DeckManager()
        self.probability_calculator = ProbabilityCalculator(self.deck_manager)

        self.create_widgets()
        self.setup_menu()

        if messagebox.askyesno("Deckliste laden?", "Möchten Sie eine gespeicherte Deckliste laden?"):
            self.deck_manager.load_deck()
        else:
            self.deck_manager.new_deck()
        self.update_deck_list()

    def create_widgets(self):
        self.deck_list_monster = self.create_listbox("Monster")
        self.deck_list_spell = self.create_listbox("Zauber")
        self.deck_list_trap = self.create_listbox("Falle")
        self.search_targets_listbox = self.create_listbox("Suchziele")

        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.create_deck_tab()
        self.create_single_card_tab()
        self.create_tags_tab()

        self.card_count_label = tk.Label(self.master, text="Main Deck (0)")
        self.card_count_label.pack()

        self.setup_listbox_layout()

    def setup_listbox_layout(self):
        self.deck_list_monster.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deck_list_spell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deck_list_trap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.search_targets_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.deck_list_monster.bind("<<ListboxSelect>>", self.show_search_targets)
        self.deck_list_spell.bind("<<ListboxSelect>>", self.show_search_targets)
        self.deck_list_trap.bind("<<ListboxSelect>>", self.show_search_targets)

    def create_deck_tab(self):
        deck_tab = ttk.Frame(self.notebook)
        self.notebook.add(deck_tab, text="Deck")

        self.add_card_button = ttk.Button(deck_tab, text="Karte hinzufügen", command=lambda: self.open_card_window())
        self.add_card_button.pack()

        self.remove_card_button = ttk.Button(deck_tab, text="Karte entfernen", command=self.remove_card)
        self.remove_card_button.pack()

        self.edit_card_button = ttk.Button(deck_tab, text="Karte bearbeiten", command=self.edit_card)
        self.edit_card_button.pack()

    def create_single_card_tab(self):
        single_card_tab = ttk.Frame(self.notebook)
        self.notebook.add(single_card_tab, text="Einzelkarte")

        self.selected_card = tk.StringVar()
        card_names = [card["name"] for card in self.deck_manager.deck]
        self.card_dropdown = ttk.Combobox(single_card_tab, textvariable=self.selected_card, values=card_names)
        self.card_dropdown.pack(padx=10, pady=10)

        calculate_button = ttk.Button(single_card_tab, text="Wahrscheinlichkeit berechnen", command=self.calculate_single_card_probability)
        calculate_button.pack(padx=10, pady=10)

    def create_tags_tab(self):
        tags_tab = ttk.Frame(self.notebook)
        self.notebook.add(tags_tab, text="Tags")

        self.selected_tags = []
        tags = ["Engine", "1-Card Starter", "Engine-Requirement", "Normal-Summon", "Extender", "Non-Engine", "Draw", "Search"]
        for tag in tags:
            var = tk.BooleanVar()
            checkbox = tk.Checkbutton(tags_tab, text=tag, variable=var)
            checkbox.pack(anchor=tk.W, padx=10, pady=2)
            self.selected_tags.append((tag, var))

        calculate_button = ttk.Button(tags_tab, text="Wahrscheinlichkeit berechnen", command=self.calculate_tags_probability)
        calculate_button.pack(padx=10, pady=10)

    def show_search_targets(self, event):
        self.search_targets_listbox.delete(0, tk.END)

        listbox = event.widget
        selected = listbox.curselection()
        if not selected:
            return

        card_name = listbox.get(selected[0]).split(' (')[0]
        card = next((card for card in self.deck_manager.deck if card["name"] == card_name), None)
        if card and "search_cards" in card:
            for search_target in card["search_cards"]:
                self.search_targets_listbox.insert(tk.END, search_target)

    def create_listbox(self, title):
        frame = tk.Frame(self.master)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(frame, text=title).pack()
        listbox = tk.Listbox(frame)
        listbox.pack(fill=tk.BOTH, expand=True)
        return listbox

    def setup_menu(self):
        menubar = tk.Menu(self.master)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Neues Deck", command=self.deck_manager.new_deck)
        filemenu.add_command(label="Öffnen", command=self.deck_manager.load_deck)
        filemenu.add_command(label="Speichern", command=self.deck_manager.save_deck)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.master.quit)
        menubar.add_cascade(label="Datei", menu=filemenu)
        self.master.config(menu=menubar)

    def update_deck_list(self):
        self.clear_listboxes()

        for card in self.deck_manager.deck:
            display_text = f"{card['name']} ({card['anzahl']})"
            if card["type"] == "Monster":
                self.deck_list_monster.insert(tk.END, display_text)
            elif card["type"] == "Zauber":
                self.deck_list_spell.insert(tk.END, display_text)
            elif card["type"] == "Falle":
                self.deck_list_trap.insert(tk.END, display_text)
        self.update_card_count_label()

    def clear_listboxes(self):
        self.deck_list_monster.delete(0, tk.END)
        self.deck_list_spell.delete(0, tk.END)
        self.deck_list_trap.delete(0, tk.END)

    def update_card_count_label(self):
        counts = {"Monster": 0, "Zauber": 0, "Falle": 0}
        for card in self.deck_manager.deck:
            counts[card["type"]] += card["anzahl"]

        total_count = sum(counts.values())
        self.card_count_label.config(text=f"Monster({counts['Monster']}) Zauber({counts['Zauber']}) Fallen({counts['Falle']}) | Main Deck({total_count})")

    def open_card_window(self, card_data=None):
        is_editing = card_data is not None
        window_title = "Karte bearbeiten" if is_editing else "Karte hinzufügen"
        card_window = tk.Toplevel(self.master)
        card_window.title(window_title)

        card_name_entry = self.create_entry(card_window, "Kartenname:")
        if is_editing:
            card_name_entry.insert(0, card_data["name"])

        card_anzahl_spinbox = self.create_spinbox(card_window, "Anzahl:")
        card_anzahl_spinbox.delete(0, tk.END)
        card_anzahl_spinbox.insert(0, card_data["anzahl"] if is_editing else 1)

        card_type_dropdown = self.create_combobox(card_window, "Kartentyp:", ["Monster", "Zauber", "Falle"])
        if is_editing:
            card_type_dropdown.set(card_data["type"])
        else:
            card_type_dropdown.set("Monster")

        tag_vars, tag_buttons = self.create_tags(card_window)
        if is_editing:
            for tag in card_data["tags"]:
                if tag in tag_vars:
                    tag_vars[tag].set(True)

        search_cards_var = tag_vars["Search"]
        search_listbox = self.create_search_listbox(card_window)
        if is_editing:
            self.populate_search_listbox(search_listbox, card_data["search_cards"])
        else:
            self.populate_search_listbox(search_listbox, self.deck_manager.deck)

        def toggle_search_listbox():
            if search_cards_var.get():
                search_listbox.grid(row=12, column=0, padx=10, pady=10, sticky="nsew")
            else:
                search_listbox.grid_forget()

        tag_buttons["Search"].config(command=toggle_search_listbox)
        toggle_search_listbox()

        def save_card():
            card_name = card_name_entry.get()
            anzahl = int(card_anzahl_spinbox.get())
            card_type = card_type_dropdown.get()
            selected_tags = [tag for tag, var in tag_vars.items() if var.get()]
            selected_search_cards = [search_listbox.get(i) for i in search_listbox.curselection()] if "Search" in selected_tags else []

            if "Search" in selected_tags and not selected_search_cards:
                messagebox.showerror("Fehler", "Bitte wählen Sie Suchziele aus.")
                return
            if not card_name:
                messagebox.showerror("Fehler", "Bitte geben Sie einen Kartennamen ein.")
                return
            if any(card["name"] == card_name and card["name"] != (card_data["name"] if is_editing else "") for card in self.deck_manager.deck):
                messagebox.showerror("Fehler", "Eine Karte mit diesem Namen ist bereits im Deck vorhanden.")
                return
            
            data = {
                    "name": card_name,
                    "anzahl": anzahl,
                    "type": card_type,
                    "tags": selected_tags,
                    "search_cards": selected_search_cards
                }

            if is_editing:
                card_data.update(data)
            else:
                self.deck_manager.deck.append(data)

            self.update_deck_list()
            card_window.destroy()

        tk.Button(card_window, text="Speichern", command=save_card).grid(row=13, column=0, columnspan=2, padx=10, pady=10)

        card_window.columnconfigure(0, weight=1)
        card_window.columnconfigure(1, weight=1)
        card_window.rowconfigure(5, weight=1)

    def create_entry(self, window, label_text):
        tk.Label(window, text=label_text).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        entry = tk.Entry(window)
        entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        return entry

    def create_spinbox(self, window, label_text):
        tk.Label(window, text=label_text).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        spinbox = tk.Spinbox(window, from_=1, to=3)
        spinbox.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        return spinbox

    def create_combobox(self, window, label_text, values):
        tk.Label(window, text=label_text).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        combobox = ttk.Combobox(window, values=values)
        combobox.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        return combobox

    def create_tags(self, window):
        tags = ["Engine", "1-Card Starter", "Engine-Requirement", "Normal-Summon", "Extender", "Non-Engine", "Draw", "Search"]
        tag_vars = {}
        tag_buttons = {}
        for i, tag in enumerate(tags):
            var = tk.BooleanVar()
            checkbutton = tk.Checkbutton(window, text=tag, variable=var)
            checkbutton.grid(row=3 + i, column=0, padx=10, pady=5, sticky="w")
            tag_buttons[tag] = checkbutton
            tag_vars[tag] = var
        return tag_vars, tag_buttons

    def create_search_listbox(self, window):
        search_listbox = tk.Listbox(window, selectmode=tk.MULTIPLE)
        search_listbox.grid(row=12, column=0, padx=10, pady=10, sticky="nsew")
        search_listbox.grid_forget()
        return search_listbox

    def edit_card(self):
        card_to_edit = self.get_selected_card(self.deck_list_monster) or self.get_selected_card(self.deck_list_spell) or self.get_selected_card(self.deck_list_trap)
        if not card_to_edit:
            messagebox.showerror("Fehler", "Bitte wählen Sie eine Karte zum Bearbeiten aus.")
            return

        card_data = next(card for card in self.deck_manager.deck if card["name"] == card_to_edit.split(' (')[0])
        self.open_card_window(card_data)

    def get_selected_card(self, listbox):
        selected = listbox.curselection()
        if selected:
            return listbox.get(selected[0])
        return None

    def populate_search_listbox(self, listbox, selected_cards):
        listbox.delete(0, tk.END)
        all_cards = [card["name"] for card in self.deck_manager.deck]
        for item in all_cards:
            listbox.insert(tk.END, item)
            if item in selected_cards:
                listbox.select_set(all_cards.index(item))

    def remove_card(self):
        card_to_remove = self.get_selected_card(self.deck_list_monster) or self.get_selected_card(self.deck_list_spell) or self.get_selected_card(self.deck_list_trap)
        if not card_to_remove:
            messagebox.showerror("Fehler", "Bitte wählen Sie eine Karte zum Entfernen aus.")
            return

        card_name = card_to_remove.split(' (')[0]
        self.deck_manager.deck = [card for card in self.deck_manager.deck if card["name"] != card_name]
        self.update_deck_list()

    def calculate_single_card_probability(self):
        card_name = self.selected_card.get().split(' (')[0]
        if not card_name:
            messagebox.showerror("Fehler", "Bitte wählen Sie eine Karte aus.")
            return

        deck_size = sum(card["anzahl"] for card in self.deck_manager.deck)
        probability = self.probability_calculator.probability_card_in_hand(deck_size, 5, card_name)
        messagebox.showinfo("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass {card_name} in der Starthand ist, beträgt {probability:.2%}")

    def calculate_tags_probability(self):
        selected_tags = [tag for tag, var in self.selected_tags if var.get()]
        if not selected_tags:
            messagebox.showerror("Fehler", "Bitte wählen Sie mindestens einen Tag aus.")
            return

        deck_size = sum(card["anzahl"] for card in self.deck_manager.deck)
        probability = self.probability_calculator.probability_only_tags(deck_size, 5, selected_tags)
        messagebox.showinfo("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass nur Karten mit den Tags {', '.join(selected_tags)} in der Starthand sind, beträgt {probability:.2%}")
