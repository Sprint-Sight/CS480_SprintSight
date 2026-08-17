from enum import Enum

class TeamType(str, Enum): # Each enum to take diff fixture of ArtifactBundle
    HIGH_PERFORMER = "high_performing_team"
    IMBALANCED_WORKLOAD = "imbalanced_team"
    STRUGGLING_TEAM = "struggling_team"