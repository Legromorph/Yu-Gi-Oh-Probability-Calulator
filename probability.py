class ProbabilityCalculator:
    def __init__(self, deck):
        self.deck = deck

    def calculate_probability_for_card(self, card_name):
        total_cards = sum(card["anzahl"] for card in self.deck.cards)
        card_count = sum(card["anzahl"] for card in self.deck.cards if card["name"] == card_name)
        return (card_count / total_cards) * 100 if total_cards else 0

    def calculate_probability_for_tags(self, tags):
        relevant_cards = [card for card in self.deck.cards if any(tag in card.get("tags", []) for tag in tags)]
        total_cards = sum(card["anzahl"] for card in self.deck.cards)
        relevant_count = sum(card["anzahl"] for card in relevant_cards)
        return (relevant_count / total_cards) * 100 if total_cards else 0
