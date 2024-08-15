from helpers import combination

class ProbabilityCalculator:
    def __init__(self, deck_manager):
        self.deck_manager = deck_manager

    def probability_card_in_hand(self, deck_size, hand_size, card_name):
        card_data = self.deck_manager.deck
        total_card_count = self.get_card_count(card_name, card_data)
        return self.prob_card_in_hand(total_card_count, deck_size, hand_size)

    def get_card_count(self, card_name, card_data):
        def tree_find(cardname, visited):
            local_count = 0
            if cardname in visited:
                return 0

            visited.add(cardname)
            
            for card in card_data:
                if card["name"] == cardname:
                    local_count += card["anzahl"]
                if cardname in card.get("search_cards", []):
                    local_count += tree_find(card["name"], visited)
            return local_count

        card = next((card for card in card_data if card["name"] == card_name), None)
    
        if card and "Engine-Requirement" not in card.get("tags", []):
            total_card_count = tree_find(card_name, set())
        elif card:
            total_card_count = card["anzahl"]
        else:
            total_card_count = 0
        
        return total_card_count

    def prob_card_in_hand(self, card_count, deck_size, hand_size):
        prob_no_card_in_hand = combination(deck_size - card_count, hand_size) / combination(deck_size, hand_size)
        return 1 - prob_no_card_in_hand

    def probability_only_tags(self, deck_size, hand_size, tags):
        num_cards_with_tags = 0
        for card in self.deck_manager.deck:
            if all(tag in card.get("tags", []) for tag in tags):
                num_cards_with_tags += card["anzahl"]

        searchable_cards = set()
        for card in self.deck_manager.deck:
            if "Search" in card.get("tags", []):
                searchable_cards.update(card.get("search_cards", []))

        num_searchable_cards = sum(
            card["anzahl"] for card in self.deck_manager.deck if card["name"] in searchable_cards
        )
        
        total_cards_with_tags = num_cards_with_tags + num_searchable_cards
        
        prob_all_with_tags = (combination(total_cards_with_tags, hand_size) /
                            combination(deck_size, hand_size))
        
        return prob_all_with_tags
    
    def calculate_single_card_probability(self):
        card_name = self.selected_card.get().split(' (')[0]
        if not card_name:
            return ("Fehler", "Bitte wählen Sie eine Karte aus.")

        deck_size = sum(card["anzahl"] for card in self.deck)
        probability = self.probability_card_in_hand(deck_size, 5, card_name, self.deck)
        return ("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass {card_name} in der Starthand ist, beträgt {probability:.2%}")

    def calculate_tags_probability(self):
        selected_tags = [tag for tag, var in self.selected_tags if var.get()]
        if not selected_tags:
            return ("Fehler", "Bitte wählen Sie mindestens einen Tag aus.")

        deck_size = sum(card["anzahl"] for card in self.deck)
        probability = self.probability_only_tags(deck_size, 5, selected_tags, self.deck)
        return ("Wahrscheinlichkeit", f"Die Wahrscheinlichkeit, dass nur Karten mit den Tags {', '.join(selected_tags)} in der Starthand sind, beträgt {probability:.2%}")
