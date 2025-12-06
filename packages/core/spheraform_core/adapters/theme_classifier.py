"""Theme classification for datasets based on title and description."""

import re
from typing import Optional, List


class ThemeClassifier:
    """
    Classify datasets into themes based on their title and description.

    Supports 5 main themes:
    - natural_environment: environment, forest, woodland, agriculture
    - built_environment: buildings, infrastructure
    - transport: roads, rail, airports, transit
    - marine: sea, shipping, marine, benthic, coastal
    - hydrology: river, surface water, wetlands, lakes, water
    """

    THEME_PATTERNS = {
        "natural_environment": [
            r"environment",
            r"forest",
            r"woodland",
            r"agriculture",
            r"farm",
            r"park",
            r"green\s*space",
            r"tree",
            r"vegetation",
            r"habitat",
            r"conservation",
            r"nature",
            r"wild\s*life",
            r"ecology",
        ],
        "built_environment": [
            r"building",
            r"structure",
            r"infrastructure",
            r"facility",
            r"construction",
            r"development",
            r"property",
            r"estate",
            r"heritage",
            r"historic",
            r"address",
            r"utilities",
            r"urban",
        ],
        "transport": [
            r"road",
            r"street",
            r"highway",
            r"motorway",
            r"rail",
            r"railway",
            r"train",
            r"airport",
            r"transit",
            r"transport",
            r"traffic",
            r"parking",
            r"station",
            r"route",
            r"path",
            r"cycle",
        ],
        "marine": [
            r"sea",
            r"ocean",
            r"marine",
            r"shipping",
            r"port",
            r"harbour",
            r"coastal",
            r"benthic",
            r"bathymetry",
            r"maritime",
            r"tide",
            r"offshore",
            r"beach",
        ],
        "hydrology": [
            r"river",
            r"stream",
            r"water",
            r"lake",
            r"pond",
            r"wetland",
            r"flood",
            r"drainage",
            r"reservoir",
            r"canal",
            r"catchment",
            r"watershed",
            r"aquifer",
            r"spring",
        ],
    }

    @classmethod
    def classify(cls, name: str, description: Optional[str] = None) -> List[str]:
        """
        Classify a dataset into one or more themes based on its name and description.

        Args:
            name: Dataset name/title
            description: Optional dataset description

        Returns:
            List of theme names that match
        """
        # Combine name and description for matching
        text = name.lower()
        if description:
            text += " " + description.lower()

        matched_themes = []

        for theme, patterns in cls.THEME_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matched_themes.append(theme)
                    break  # Only add theme once even if multiple patterns match

        return matched_themes
