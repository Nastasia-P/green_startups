"""Filter green startups from the cleaned dataset.

A company is considered "green" if any of the taxonomy's pitchbook_keywords
appears (as a whole word/phrase, case-insensitive) in its Keywords or
Description column. The output keeps all original columns and adds a
matched_keywords column listing which green terms triggered the match.

Keywords are taken verbatim from the provided EU-taxonomy table
(pitchbook_keywords column only).
"""

import csv
import re

import pandas as pd

INPUT_PATH = "startups_cleaned.csv"
OUTPUT_PATH = "green_startups.csv"
SEARCH_COLUMNS = ["Keywords", "Description"]

# pitchbook_keywords, grouped by the taxonomy appendix they come from.
PITCHBOOK_KEYWORDS = [
    # A.1 - Climate change mitigation
    "anaerobic digestion",
    "bioenergy", "biomass energy",
    "biodiesel", "bioethanol", "biofuel",
    "biogas", "biomethane",
    "carbon accounting", "emissions monitoring",
    "carbon capture", "carbon storage", "ccs", "co2 capture", "co2 storage",
    "carbon removal",
    "carbon offsets",
    "compost", "composting",
    "concentrated solar power", "concentrating solar",
    "cycle logistics", "micromobility", "personal mobility",
    "district cooling", "district heating",
    "charging infrastructure", "charging point", "charging station",
    "electric vehicle", "electric vehicle battery", "ev charging",
    "electrolyser",
    "energy efficiency", "energy efficient",
    "building retrofit", "energy performance", "insulation",
    "battery storage", "electricity storage", "energy storage", "grid storage",
    "rechargeable battery", "solid-state battery", "battery management system",
    "second life battery",
    "geothermal",
    "emission reduction", "ghg emission", "greenhouse gas",
    "heat pump",
    "hydrogen",
    "hydroelectric", "hydropower",
    "landfill gas",
    "low carbon",
    "green steel", "low-carbon cement",
    "material recovery",
    "ocean energy", "tidal energy", "tidal power", "wave energy",
    "rail freight",
    "renewable energy", "renewable power",
    "smart grid", "demand response", "energy management system",
    "solar",
    "photovoltaic", "solar photovoltaic",
    "sustainable aviation fuel",
    "waste heat",
    "offshore wind", "onshore wind", "wind energy", "wind farm", "wind power",
    "wind turbine",
    # A.2 - Climate change adaptation
    "climate adaptation", "climate change adaptation", "climate resilience",
    "flood defence",
    # A.3 - Sustainable use and protection of water and marine resources
    "desalination",
    "leak detection", "leakage reduction",
    "sewage", "sewerage", "wastewater",
    "water collection", "water purification", "water supply", "water treatment",
    # A.4 - Transition to a circular economy
    "battery recycling",
    "bio waste", "biowaste", "organic waste",
    "circular economy",
    "sustainable packaging",
    "e-waste",
    "depollution", "dismantling", "end of life",
    "food waste reduction",
    "hazardous waste",
    "phosphorus recovery",
    "plastic packaging", "plastic recycling",
    "product as a service",
    "re-use", "reuse",
    "recycle", "recycled", "recycling",
    "refurbish", "refurbishment", "remanufacturing",
    "second hand", "used goods",
    "waste collection", "waste management", "waste recovery", "waste sorting",
    "grey water", "greywater", "rainwater harvesting", "reclaimed water",
    # A.5 - Pollution prevention and control
    "air quality", "air quality monitoring", "pollution control",
    "pollution prevention",
    "environmental remediation", "groundwater remediation", "land remediation",
    "remediation activities", "remediation service", "site remediation",
    "soil remediation", "water remediation",
    # A.6 - Protection and restoration of biodiversity and ecosystems
    "afforestation", "reforestation",
    "biodiversity",
    "ecosystem restoration", "ecosystem service", "marine ecosystem",
    "regenerative agriculture", "precision farming", "vertical farming",
    "alternative protein", "soil health",
    "forest management", "sustainable forestry",
    "habitat conservation", "habitat protection", "habitat restoration",
    "marine conservation",
    "nature-based solution",
    "wetland restoration",
]


def build_pattern(keywords):
    """Compile one case-insensitive regex matching any keyword as a whole term.

    Keywords are sorted longest-first so multi-word phrases are preferred over
    their shorter substrings (e.g. "solar photovoltaic" over "solar").
    """
    unique = sorted(set(k.lower() for k in keywords), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in unique)
    return re.compile(r"(?<!\w)(?:" + alternation + r")(?!\w)", re.IGNORECASE)


def main():
    pattern = build_pattern(PITCHBOOK_KEYWORDS)

    df = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False)
    total = len(df)

    haystack = df[SEARCH_COLUMNS[0]].str.cat(
        [df[c] for c in SEARCH_COLUMNS[1:]], sep=" \u241f "
    )

    def find_matches(text):
        hits = pattern.findall(text)
        if not hits:
            return None
        seen = []
        for h in hits:
            k = h.lower()
            if k not in seen:
                seen.append(k)
        return ", ".join(seen)

    df["matched_keywords"] = haystack.map(find_matches)

    green = df[df["matched_keywords"].notna()].copy()
    green.to_csv(OUTPUT_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    print(f"Total startups:  {total}")
    print(f"Green startups:  {len(green)} ({len(green) / total:.1%})")
    print(f"Output:          {OUTPUT_PATH}")

    top = (
        green["matched_keywords"]
        .str.split(", ")
        .explode()
        .value_counts()
        .head(15)
    )
    print("\nTop matched keywords:")
    for kw, cnt in top.items():
        print(f"  {cnt:>6}  {kw}")


if __name__ == "__main__":
    main()
