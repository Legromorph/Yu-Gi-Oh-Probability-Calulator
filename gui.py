import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from deck import Deck
from probability import ProbabilityCalculator

class YugiohProbabilityCalculatorGUI:
    def __init__(self, master):
        self.master = master
        master.title("Yu-Gi-Oh! Wahrscheinlichkeitsrechner")

        # Initialize the deck and probability calculator
        self.deck = Deck()
        self.probability_calculator = ProbabilityCalculator(self.deck)

        # Create and place GUI elements
        self.create_widgets()
        self.setup_menu()

        # Load existing deck or create a new one
        if messagebox.askyesno("Deckliste laden?", "Möchten Sie eine gespeicherte Deckliste laden?"):
            self.load_deck()
        else:
            self.new_deck()

    def create_widgets(self):
        # Erstelle Listboxes für verschiedene Kartentypen
        self.deck_list_monster = self.create_listbox("Monster")
        self.deck_list_spell = self.create_listbox("Zauber")
        self.deck_list_trap = self.create_listbox("Falle")
        self.search_targets_listbox = self.create_listbox("Suchziele")

        # Erstelle einen Notebook-Widget (Tab-Control)
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Füge die Reiter hinzu
        self.create_deck_tab()
        self.create_single_card_tab()
        self.create_tags_tab()

        # Erstelle Kartenanzahl-Label
        self.card_count_label = tk.Label(self.master, text="Main Deck (0)")
        self.card_count_label.pack()

        # Setze die Listboxen nebeneinander
        self.setup_listbox_layout()

    def setup_listbox_layout(self):
        # Anordnung der Listboxen nebeneinander
        self.deck_list_monster.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deck_list_spell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deck_list_trap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.search_targets_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Setze eine Funktion für das Selektieren von Karten in den Listboxen
        self.deck_list_monster.bind("<<ListboxSelect>>", self.show_search_targets)
        self.deck_list_spell.bind("<<ListboxSelect>>", self.show_search_targets)
        self.deck_list_trap.bind("<<ListboxSelect>>", self.show_search_targets)

    def create_deck_tab(self):
        deck_tab = ttk.Frame(self.notebook)
        self.notebook.add(deck_tab, text="Deck")

        # Füge Aktions-Buttons hinzu
        self.add_card_button = ttk.Button(deck_tab, text="Karte hinzufügen", command=self.open_card_window)
        self.add_card_button.pack()

        self.remove_card_button = ttk.Button(deck_tab, text="Karte entfernen", command=self.remove_card)
        self.remove_card_button.pack()

        self.edit_card_button = ttk.Button(deck_tab, text="Karte bearbeiten", command=self.edit_card)
        self.edit_card_button.pack()

    def create_single_card_tab(self):
        single_card_tab = ttk.Frame(self.notebook)
        self.notebook.add(single_card_tab, text="Einzelkarte")

        # Dropdown Menü für die Auswahl einer Karte
        self.selected_card = tk.StringVar()
        card_names = [card["name"] for card in self.deck.cards]
        self.card_dropdown = ttk.Combobox(single_card_tab, textvariable=self.selected_card, values=card_names)
        self.card_dropdown.pack(padx=10, pady=10)

        # Button für die Einzelkarten-Wahrscheinlichkeitsberechnung
        calculate_button = ttk.Button(single_card_tab, text="Wahrscheinlichkeit berechnen", command=self.calculate_single_card_probability)
        calculate_button.pack(padx=10, pady=10)

    def create_tags_tab(self):
        tags_tab = ttk.Frame(self.notebook)
        self.notebook.add(tags_tab, text="Tags")

        # Mehrfachauswahl für Tags
        self.selected_tags = []
        tags = ["Engine", "1-Card Starter", "Engine-Requirement", "Normal-Summon", "Extender", "Non-Engine", "Draw", "Search"]
        for tag in tags:
            var = tk.BooleanVar()
            checkbox = tk.Checkbutton(tags_tab, text=tag, variable=var)
            checkbox.pack(anchor=tk.W, padx=10, pady=2)
            self.selected_tags.append((tag, var))

        # Button für die Tags-Wahrscheinlichkeitsberechnung
        calculate_button = ttk.Button(tags_tab, text="Wahrscheinlichkeit berechnen", command=self.calculate_tags_probability)
        calculate_button.pack(padx=10, pady=10)

    def show_search_targets(self, event):
        # Leere die Suchziele Listbox
        self.search_targets_listbox.delete(0, tk.END)

        # Finde die ausgewählte Karte in der Listbox
        listbox = event.widget
        selected = listbox.curselection()
        if not selected:
            return

        card_name = listbox.get(selected[0]).split(' (')[0]

        # Finde die Karte in der Deck-Liste
        card = next((card for card in self.deck.cards if card["name"] == card_name), None)
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
        filemenu.add_command(label="Neues Deck", command=self.new_deck)
        filemenu.add_command(label="Öffnen", command=self.load_deck)
        filemenu.add_command(label="Speichern", command=self.save_deck)
        filemenu.add_separator()
        filemenu.add_command(label="Beenden", command=self.master.quit)
        menubar.add_cascade(label="Datei", menu=filemenu)
        self.master.config(menu=menubar)

    def save_deck(self, file_path=None):
        if file_path is None and self.deck.file_path is None:
            file_path = filedialog.asksaveasfilename(defaultextension=".json")
        elif file_path is None:
            file_path = self.deck.file_path

        if file_path:
            self.deck.save(file_path)

    def load_deck(self):
        file_path = filedialog.askopenfilename(defaultextension=".json")
        if file_path:
            self.deck.load(file_path)
            self.update_deck_list()

    def new_deck(self):
        self.deck.clear()
        self.update_deck_list()

    def update_deck_list(self):
        self.clear_listboxes()

        for card in self.deck.cards:
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
        for card in self.deck.cards:
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

        save_button = ttk.Button(card_window, text="Speichern", command=lambda: self.save_card(card_data, card_name_entry.get(), int(card_anzahl_spinbox.get()), card_type_dropdown.get(), card_window))
        save_button.pack(padx=10, pady=10)

    def create_entry(self, parent, label_text):
        frame = ttk.Frame(parent)
        frame.pack(padx=10, pady=5)
        label = ttk.Label(frame, text=label_text)
        label.pack(side=tk.LEFT)
        entry = ttk.Entry(frame)
        entry.pack(side=tk.LEFT)
        return entry

    def create_spinbox(self, parent, label_text):
        frame = ttk.Frame(parent)
        frame.pack(padx=10, pady=5)
        label = ttk.Label(frame, text=label_text)
        label.pack(side=tk.LEFT)
        spinbox = ttk.Spinbox(frame, from_=1, to=99)
        spinbox.pack(side=tk.LEFT)
        return spinbox

    def create_combobox(self, parent, label_text, values):
        frame = ttk.Frame(parent)
        frame.pack(padx=10, pady=5)
        label = ttk.Label(frame, text=label_text)
        label.pack(side=tk.LEFT)
        combobox = ttk.Combobox(frame, values=values)
        combobox.pack(side=tk.LEFT)
        return combobox

    def save_card(self, card_data, name, anzahl, card_type, window):
        if not name or not anzahl or not card_type:
            messagebox.showwarning("Warnung", "Bitte alle Felder ausfüllen.")
            return

        if card_data:
            card_data.update({"name": name, "anzahl": anzahl, "type": card_type})
        else:
            self.deck.add_card({"name": name, "anzahl": anzahl, "type": card_type})

        self.update_deck_list()
        window.destroy()

    def remove_card(self):
        selected = self.deck_list_monster.curselection() + self.deck_list_spell.curselection() + self.deck_list_trap.curselection()
        if not selected:
            messagebox.showwarning("Warnung", "Bitte eine Karte auswählen.")
            return

        listbox = self.deck_list_monster if self.deck_list_monster.curselection() else (self.deck_list_spell if self.deck_list_spell.curselection() else self.deck_list_trap)
        card_name = listbox.get(selected[0]).split(' (')[0]
        self.deck.remove_card(card_name)
        self.update_deck_list()

    def edit_card(self):
        selected = self.deck_list_monster.curselection() + self.deck_list_spell.curselection() + self.deck_list_trap.curselection()
        if not selected:
            messagebox.showwarning("Warnung", "Bitte eine Karte auswählen.")
            return

        listbox = self.deck_list_monster if self.deck_list_monster.curselection() else (self.deck_list_spell if self.deck_list_spell.curselection() else self.deck_list_trap)
        card_name = listbox.get(selected[0]).split(' (')[0]
        card_data = next(card for card in self.deck.cards if card["name"] == card_name)
        self.open_card_window(card_data)

    def calculate_single_card_probability(self):
        card_name = self.selected_card.get()
        if not card_name:
            messagebox.showwarning("Warnung", "Bitte eine Karte auswählen.")
            return

        probability = self.probability_calculator.calculate_probability_for_card(card_name)
        messagebox.showinfo("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass {card_name} gezogen wird, beträgt {probability:.2f}%.")

    def calculate_tags_probability(self):
        selected_tags = [tag for tag, var in self.selected_tags if var.get()]
        if not selected_tags:
            messagebox.showwarning("Warnung", "Bitte mindestens einen Tag auswählen.")
            return

        probability = self.probability_calculator.calculate_probability_for_tags(selected_tags)
        tags_str = ", ".join(selected_tags)
        messagebox.showinfo("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass eine Karte mit den Tags ({tags_str}) gezogen wird, beträgt {probability:.2f}%.")
