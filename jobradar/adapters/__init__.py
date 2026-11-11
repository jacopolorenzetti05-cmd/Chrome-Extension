"""Adapters – one module per hiring-system type.

Every adapter module exposes:

    fetch(src: dict) -> list[Posting]        # required: all current postings of the source
    detail(src: dict, p: Posting) -> None    # optional: fill description/salary/deadline for one posting

`src` is the entry from sources.yaml (name, sector, params, ...). Adapters must only
read the employer's own hiring system (ATS API or official careers domain).
"""
from __future__ import annotations

import importlib

ADAPTERS = [
    "greenhouse", "lever", "smartrecruiters", "workable", "recruitee", "personio", "teamtailor",
    "ashby", "workday", "successfactors", "jobylon", "html",
    # additional hiring systems found during discovery
    "oracle", "pinpoint", "softgarden", "phenom", "eightfold", "brassring", "beesite",
    "gs", "hibob", "digitalrecruiters", "puma",
]


def get(name: str):
    if name not in ADAPTERS:
        raise KeyError(f"unknown adapter '{name}'. Known: {', '.join(ADAPTERS)}")
    return importlib.import_module(f"{__name__}.{name}")
