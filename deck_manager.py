import json
from tkinter import filedialog

class DeckManager:
    def __init__(self):
        self.deck = []
        self.current_file_path = None

    def save_deck(self, file_path=None):
        if file_path is None and self.current_file_path is None:
            file_path = filedialog.asksaveasfilename(defaultextension=".json")
        elif file_path is None:
            file_path = self.current_file_path

        if file_path:
            with open(file_path, "w") as f:
                json.dump(self.deck, f)
            self.current_file_path = file_path

    def load_deck(self):
        file_path = filedialog.askopenfilename(defaultextension=".json")
        if file_path:
            with open(file_path, "r") as f:
                self.deck = json.load(f)
            self.current_file_path = file_path

    def new_deck(self):
        self.deck = []

    # Weitere Funktionen zum Bearbeiten des Decks hinzufügen
