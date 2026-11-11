"""History logic: no duplicates, Removed only after two consecutive misses."""
import importlib

from jobradar.models import Posting


def test_two_runs_no_duplicates_and_removal(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB", str(tmp_path / "t.db"))
    from jobradar import config
    importlib.reload(config)
    from jobradar import pipeline, store as store_mod
    importlib.reload(store_mod)
    importlib.reload(pipeline)
    st = store_mod.Store(tmp_path / "t.db")
    src = {"key": "x", "name": "X", "sector": "sports", "adapter": "greenhouse", "params": {}, "country": "CH"}

    def recs(ids):
        posts = [Posting(id=f"x:{i}", company="X", title="Partnerships Intern", location="Zurich",
                         url=f"https://example.org/{i}", description_text="d") for i in ids]
        return pipeline.classify_and_enrich(src, posts, st, {}, False)

    pipeline._apply_history(st, "x", recs([1, 2]), "2026-11-10", "t1")
    pipeline._apply_history(st, "x", recs([1, 2]), "2026-11-11", "t2")
    rows = st.all()
    assert len(rows) == 2 and all(r["status"] == "active" for r in rows)
    pipeline._apply_history(st, "x", recs([1]), "2026-11-12", "t3")
    assert st.get("x:2")["status"] == "active" and st.get("x:2")["consecutive_misses"] == 1
    pipeline._apply_history(st, "x", recs([1]), "2026-11-13", "t4")
    assert st.get("x:2")["status"] == "removed"
    pipeline._apply_history(st, "x", recs([1, 2]), "2026-11-14", "t5")
    assert st.get("x:2")["status"] == "active" and st.get("x:2")["first_seen"] == "2026-11-10"
    assert len(st.all()) == 2
