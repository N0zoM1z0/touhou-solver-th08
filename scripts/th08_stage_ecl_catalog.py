"""Pinned decoded ECL identities for original-game Practice Start stages.

The route index is the value exposed by the shipped runtime.  The digest pins
the decoded image that is compared with the relocated runtime image before any
source-derived planning fact may receive action authority.
"""

from __future__ import annotations

from dataclasses import dataclass


SCALE_MODEL_NO_WRITER = "exact_no_scale_writer"
SCALE_MODEL_DYNAMIC = "dynamic_scale_source_required"
SCALE_MODEL_FINAL_B = "finalb_complete_scale_source"


@dataclass(frozen=True, slots=True)
class StageEclIdentity:
    practice_key: str
    route_index: int
    label: str
    filename: str
    sha256: str
    scale_model: str


PRACTICE_STAGE_ECL_IDENTITIES = {
    "1": StageEclIdentity(
        "1",
        0,
        "Stage 1",
        "ecldata1.ecl",
        "6b44a0ea36648edcdeae522a2ac16d1f09bf2097d3ddaa1a61c8c1703bad68ea",
        SCALE_MODEL_NO_WRITER,
    ),
    "2": StageEclIdentity(
        "2",
        1,
        "Stage 2",
        "ecldata2.ecl",
        "a1b183c4e1c9d939290192f84e50ac551e31a5abe91ac396e5b056a813051a10",
        SCALE_MODEL_NO_WRITER,
    ),
    "3": StageEclIdentity(
        "3",
        2,
        "Stage 3",
        "ecldata3.ecl",
        "113e52b73dfdd94408b99dd7646ac973554cef76f1b7bd6686a773da6e974ce8",
        SCALE_MODEL_NO_WRITER,
    ),
    "4a": StageEclIdentity(
        "4a",
        3,
        "Stage 4A / Reimu",
        "ecldata4a.ecl",
        "797c83391c77d386abd264249224821be3d878fcf73b2bd71189dbfd3776f6cf",
        SCALE_MODEL_NO_WRITER,
    ),
    "4b": StageEclIdentity(
        "4b",
        4,
        "Stage 4B / Marisa",
        "ecldata4b.ecl",
        "aa4c1d45accc12faa9fab021f3ba6a19f668e1edeaafcad04293483d4b18bcc6",
        SCALE_MODEL_NO_WRITER,
    ),
    "5": StageEclIdentity(
        "5",
        5,
        "Stage 5",
        "ecldata5.ecl",
        "3148f45faf78bd8211a956edcdc353be73d2781995d3dadd36bdca8132f8fe19",
        SCALE_MODEL_NO_WRITER,
    ),
    "6a": StageEclIdentity(
        "6a",
        6,
        "Final A / Eirin",
        "ecldata6.ecl",
        "3ede62afec737de7970ab979e14db0e6433d1eff43eac3a036a6df10ba821f72",
        SCALE_MODEL_DYNAMIC,
    ),
    "6b": StageEclIdentity(
        "6b",
        7,
        "Final B / Kaguya",
        "ecldata7.ecl",
        "20b35dca3820438f0b90ae44e3362a7af27d2fc1ac7ae5888c477dc1c89a3734",
        SCALE_MODEL_FINAL_B,
    ),
}

PRACTICE_STAGE_KEYS = tuple(PRACTICE_STAGE_ECL_IDENTITIES)
NO_SCALE_WRITER_STAGE_ROUTE_INDICES = frozenset(
    identity.route_index
    for identity in PRACTICE_STAGE_ECL_IDENTITIES.values()
    if identity.scale_model == SCALE_MODEL_NO_WRITER
)
FINAL_B_ECL_SHA256 = PRACTICE_STAGE_ECL_IDENTITIES["6b"].sha256


__all__ = [
    "FINAL_B_ECL_SHA256",
    "NO_SCALE_WRITER_STAGE_ROUTE_INDICES",
    "PRACTICE_STAGE_ECL_IDENTITIES",
    "PRACTICE_STAGE_KEYS",
    "SCALE_MODEL_DYNAMIC",
    "SCALE_MODEL_FINAL_B",
    "SCALE_MODEL_NO_WRITER",
    "StageEclIdentity",
]
