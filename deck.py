import json

class Deck:
    def __init__(self):
        self.cards = []
        self.file_path = None

    def add_card(self, card):
        self.cards.append(card)

    def remove_card(self, card_name):
        self.cards = [card for card in self.cards if card["name"] != card_name]

    def clear(self):
        self.cards = []

    def save(self, file_path):
        with open(file_path, 'w') as f:
            json.dump(self.cards, f, indent=4)
        self.file_path = file_path

    def load(self, file_path):
        with open(file_path, 'r') as f:
            self.cards = json.load(f)
        self.file_path = file_path
