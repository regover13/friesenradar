"""Start und Ende in den Live-Kästen von Kutter, Bummel und Reddung (Wunsch 24.10.2026).

Bis dahin zeigte der Kutter keine Zeit, der Bummel auch nicht, die Reddung nur „Ende 21:00 UTC".
Jetzt dieselbe Zeile wie in der Bummel-Ansicht: „24.10. 19:00z – 21:00z".
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _funktion(name):
    m = re.search(r"\n(?:async )?function " + name + r"\(.*?\n}\n", INDEX, re.S)
    assert m, name
    return m.group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")
@pytest.mark.parametrize("start, ende, erwartet", [
    ("2026-10-24T19:00:00Z", "2026-10-24T21:00:00Z", "24.10. 19:00z – 21:00z"),
    ("2026-10-24T22:00:00Z", "2026-10-25T01:00:00Z", "24.10. 22:00z – 25.10. 01:00z"),
    (None, None, None),
])
def test_zeile_mit_dem_zeitfenster(start, ende, erwartet):
    js = (_funktion("_bummelTagUndZeit") + _funktion("_bummelNurZeit") + _funktion("_bummelZeitfenster")
          + "function icon(n) { return '<i>'; }\nfunction escHtml(s) { return s; }\n" + _funktion("_liveZeitfensterZeile")
          + f"\nconsole.log(JSON.stringify(_liveZeitfensterZeile({json.dumps(start)}, {json.dumps(ende)})));")
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    if erwartet is None:
        assert out == ""
    else:
        assert erwartet in out and 'class="bb-sub"' in out


@pytest.mark.parametrize("block, ausdruck", [
    ("_kutterBannerBlock", "_liveZeitfensterZeile(d.dtstart, d.dtend)"),
    ("fetchBummelActive", "_liveZeitfensterZeile(v.dtstart, v.dtend)"),
    ("_reddungBannerBlock", "_liveZeitfensterZeile(r.dtstart, r.dtend)"),
])
def test_jeder_live_kasten_zeigt_das_zeitfenster(block, ausdruck):
    assert ausdruck in _funktion(block)


def test_reddung_nennt_das_ende_nicht_doppelt():
    assert "Ende ${ende} UTC" not in _funktion("_reddungBannerBlock")
