"""Pinned decoded ECL identities for original-game execution modes.

The route index is the value exposed by the shipped runtime.  The digest pins
the decoded image that is compared with the relocated runtime image before any
source-derived planning fact may receive action authority.  Route play and
Practice Start both load the ordinary ``*.ecl`` image: the loader tests the
game-manager ``isSpellPractice`` bit, not ``isPracticeMode``.  Stage-scoped
Spell Practice below card 205 instead loads ``*sp.ecl``.  Keeping the latter
identities explicitly named is mandatory because their subroutine layouts can
differ even when their normalized spell programs are equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass


SCALE_MODEL_NO_WRITER = "exact_no_scale_writer"
SCALE_MODEL_DYNAMIC = "dynamic_scale_source_required"
SCALE_MODEL_FINAL_B = "finalb_complete_scale_source"


@dataclass(frozen=True, slots=True)
class StageEclIdentity:
    stage_key: str
    route_index: int
    label: str
    filename: str
    sha256: str
    scale_model: str


ROUTE_STAGE_ECL_IDENTITIES = {
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

# Practice Start sets GameManagerFlags::isPracticeMode (bit 0), but the ECL
# branch in EnemyManager::AddedCallback tests isSpellPractice (bit 14).
# Preserve a separate mapping name at call sites so the requested execution
# mode remains explicit even though the pinned identities equal route play.
PRACTICE_STAGE_ECL_IDENTITIES = dict(ROUTE_STAGE_ECL_IDENTITIES)


# g_StageSpellEclFiles: used by Spell Practice while the selected card number
# is below 205.  Cards 205 and above use the per-card g_SpellEclFiles table and
# are intentionally outside this stage-indexed catalog.
STAGE_SPELL_PRACTICE_ECL_IDENTITIES = {
    "1": StageEclIdentity(
        "1",
        0,
        "Stage 1",
        "ecldata1sp.ecl",
        "aac506b4eaf8fdfaa90e876f74db711d3c0724f63798e7d62801b02bbb29e00e",
        SCALE_MODEL_NO_WRITER,
    ),
    "2": StageEclIdentity(
        "2",
        1,
        "Stage 2",
        "ecldata2sp.ecl",
        "2f83c57da937f35288f6f0e1b6ef3aecddd25b4e80fbc3ed5ef7289bef2229f1",
        SCALE_MODEL_NO_WRITER,
    ),
    "3": StageEclIdentity(
        "3",
        2,
        "Stage 3",
        "ecldata3sp.ecl",
        "3d458ec6549f1d7fb6c694388adb55c010ac4cb405457ab9af6df2e13928ca5f",
        SCALE_MODEL_NO_WRITER,
    ),
    "4a": StageEclIdentity(
        "4a",
        3,
        "Stage 4A / Reimu",
        "ecldata4asp.ecl",
        "9ac983ec5a34fd607b73891d5ba95a19caadb493565b8986320c04d0de8a8df3",
        SCALE_MODEL_NO_WRITER,
    ),
    "4b": StageEclIdentity(
        "4b",
        4,
        "Stage 4B / Marisa",
        "ecldata4bsp.ecl",
        "007da9d02374f01292eada9a065c21b54cebbb81a5bff7a1660753498df65b51",
        SCALE_MODEL_NO_WRITER,
    ),
    "5": StageEclIdentity(
        "5",
        5,
        "Stage 5",
        "ecldata5sp.ecl",
        "d9140821aae21c9426f7ebb0a4e8334718265bdd011f20b7c026eda901639d4b",
        SCALE_MODEL_NO_WRITER,
    ),
    "6a": StageEclIdentity(
        "6a",
        6,
        "Final A / Eirin",
        "ecldata6sp.ecl",
        "c1cd463702f1e621b67d1e2f4915fd3e3a27ac61687ef477f4ff1bde554a44d7",
        SCALE_MODEL_DYNAMIC,
    ),
    "6b": StageEclIdentity(
        "6b",
        7,
        "Final B / Kaguya",
        "ecldata7sp.ecl",
        "7f1a847fdd7ceb5e35dfd3529a54961ab4d1c9e7607fbcfb577936465326ab0e",
        SCALE_MODEL_FINAL_B,
    ),
}

PRACTICE_STAGE_KEYS = tuple(PRACTICE_STAGE_ECL_IDENTITIES)
NO_SCALE_WRITER_STAGE_ROUTE_INDICES = frozenset(
    identity.route_index
    for identity in ROUTE_STAGE_ECL_IDENTITIES.values()
    if identity.scale_model == SCALE_MODEL_NO_WRITER
)
FINAL_B_ECL_SHA256 = ROUTE_STAGE_ECL_IDENTITIES["6b"].sha256


__all__ = [
    "FINAL_B_ECL_SHA256",
    "NO_SCALE_WRITER_STAGE_ROUTE_INDICES",
    "PRACTICE_STAGE_ECL_IDENTITIES",
    "PRACTICE_STAGE_KEYS",
    "ROUTE_STAGE_ECL_IDENTITIES",
    "STAGE_SPELL_PRACTICE_ECL_IDENTITIES",
    "SCALE_MODEL_DYNAMIC",
    "SCALE_MODEL_FINAL_B",
    "SCALE_MODEL_NO_WRITER",
    "StageEclIdentity",
]
