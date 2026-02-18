"""Realistic make/model lookup table for car generation."""

# Map of make → list of models
MAKES_MODELS: dict[str, list[str]] = {
    "Toyota": ["Camry", "Corolla", "RAV4", "Tacoma", "4Runner", "Highlander"],
    "Honda": ["Civic", "Accord", "CR-V", "Pilot", "HR-V", "Odyssey"],
    "Ford": ["F-150", "Escape", "Explorer", "Mustang", "Edge", "Bronco"],
    "Chevrolet": ["Silverado", "Equinox", "Malibu", "Traverse", "Colorado", "Tahoe"],
    "BMW": ["3 Series", "5 Series", "X3", "X5", "7 Series", "X1"],
    "Mercedes-Benz": ["C-Class", "E-Class", "GLC", "GLE", "S-Class", "A-Class"],
    "Audi": ["A4", "Q5", "A6", "Q7", "A3", "Q3"],
    "Tesla": ["Model 3", "Model Y", "Model S", "Model X"],
    "Jeep": ["Grand Cherokee", "Wrangler", "Cherokee", "Compass", "Gladiator"],
    "RAM": ["1500", "2500", "3500", "ProMaster"],
    "Hyundai": ["Elantra", "Tucson", "Santa Fe", "Sonata", "Palisade", "Kona"],
    "Kia": ["Forte", "Sportage", "Telluride", "Soul", "Sorento", "Carnival"],
    "Subaru": ["Outback", "Forester", "Crosstrek", "Impreza", "Legacy", "Ascent"],
    "Mazda": ["Mazda3", "CX-5", "Mazda6", "CX-9", "MX-5 Miata", "CX-50"],
    "Nissan": ["Altima", "Rogue", "Sentra", "Pathfinder", "Frontier", "Murano"],
    "Volkswagen": ["Jetta", "Tiguan", "Atlas", "Passat", "Golf", "Taos"],
    "Dodge": ["Challenger", "Charger", "Durango", "Journey"],
    "Chrysler": ["300", "Pacifica", "Voyager"],
}

# All makes as a flat list for convenience
ALL_MAKES: list[str] = list(MAKES_MODELS.keys())


def get_all_combinations() -> list[tuple[str, str]]:
    """Return all (make, model) pairs."""
    combos = []
    for make, models in MAKES_MODELS.items():
        for model in models:
            combos.append((make, model))
    return combos
