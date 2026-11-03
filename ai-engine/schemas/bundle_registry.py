from collections import OrderedDict
from schemas.artifact_bundle import ArtifactBundle

_MAX = 32
_BUNDLES: "OrderedDict[tuple[str, str], ArtifactBundle]" = OrderedDict()

def remember_bundle(bundle: ArtifactBundle) -> None:
    _BUNDLES[(bundle.team_id, bundle.sprint_id)] = bundle
    _BUNDLES.move_to_end((bundle.team_id, bundle.sprint_id))
    while len(_BUNDLES) > _MAX:
        _BUNDLES.popitem(last=False)

def get_bundle(team_id: str | None, sprint_id: str | None) -> ArtifactBundle | None:
    return _BUNDLES.get((team_id, sprint_id))