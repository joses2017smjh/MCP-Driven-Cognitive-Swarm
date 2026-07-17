"""Shared demo squad tables.

Both demo backends (data server: squad shares; news server: availability
parsing) must agree on player identities, exactly as real providers agree on
player IDs. Real deployments replace this with the providers' own ID space.
"""

from __future__ import annotations

DEMO_SQUADS: dict[str, dict[str, list[str]]] = {
    "ARS": {"Bukayo Saka": ["Saka"], "Martin Odegaard": ["Odegaard"],
            "Gabriel Jesus": ["Jesus"], "Declan Rice": ["Rice"]},
    "MCI": {"Erling Haaland": ["Haaland"], "Phil Foden": ["Foden"],
            "Rodri": [], "Kevin De Bruyne": ["De Bruyne", "KDB"]},
    "LIV": {"Mohamed Salah": ["Salah"], "Virgil van Dijk": ["van Dijk"]},
    "RMA": {"Vinicius Junior": ["Vinicius"], "Jude Bellingham": ["Bellingham"]},
    "BAR": {"Lamine Yamal": ["Yamal"], "Pedri": []},
    "BAY": {"Harry Kane": ["Kane"], "Jamal Musiala": ["Musiala"]},
    "PSG": {"Ousmane Dembele": ["Dembele"], "Vitinha": []},
}
