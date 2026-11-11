"""One live smoke test per adapter (network required). Run: pytest -m live"""
import pytest

from jobradar import adapters, config

pytestmark = pytest.mark.live

SOURCES = {s["adapter"]: s for s in reversed(config.load_sources()) if s.get("enabled", True)}
# adapters that are implemented but not used by any source get a known public board
EXTRA = {
    "lever": {"key": "leverdemo", "name": "Lever demo", "sector": "sports", "adapter": "lever", "params": {"company": "leverdemo"}},
    "ashby": {"key": "ashby", "name": "Ashby", "sector": "sports", "adapter": "ashby", "params": {"org": "sorare"}},
    "workable": {"key": "workable", "name": "Workable", "sector": "sports", "adapter": "workable", "params": {"account": "workable"}},
}


@pytest.mark.parametrize("adapter", adapters.ADAPTERS)
def test_adapter_live(adapter):
    src = SOURCES.get(adapter) or EXTRA.get(adapter)
    if not src:
        pytest.skip(f"no source configured for {adapter}")
    src = dict(src, params=dict(src["params"]))
    posts = adapters.get(adapter).fetch(src)
    assert isinstance(posts, list)
    for p in posts[:20]:
        assert p.title and p.url.startswith("http")
        assert not config.is_aggregator(p.url)
