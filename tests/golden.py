# tests/golden.py
"""The golden case matrix: a field-by-field mirror of KT/strokes.ts's
buildCorpus()/GLYPH_CASES.

⚠ The three buhin data strings in GLYPH_CASES must be copied character for
character from KT/strokes.ts:76-106 (glyph:u6f22 / glyph:stretch /
glyph:transform, including the names arrays). This file does not inline those
strings, to avoid transcription typos — the implementer opens the source file
and copies them.
"""
from pathlib import Path

STROKE_TYPES = [1, 2, 3, 4, 6, 7]
HEAD_TYPES = [0, 1, 2, 6, 7, 12, 22, 27, 32]
TAIL_TYPES = [0, 1, 2, 4, 5, 7, 8, 13, 14, 15, 23, 24, 32, 313, 413]
GEOMETRIES = {
    "h": [20, 50, 80, 50, 140, 50, 180, 50],
    "v": [50, 20, 50, 80, 50, 140, 50, 180],
    "d": [30, 30, 70, 80, 120, 130, 170, 175],
    "rl": [180, 150, 120, 120, 70, 80, 20, 30],
}
POINT_COUNT = {1: 2, 2: 3, 3: 3, 4: 3, 6: 4, 7: 4}

GLYPH_CASES = [
    {
        "id": "glyph:u6f22",
        "buhin": {
            "u6f22": "99:150:0:9:12:73:200:u6c35-07:0:-10:50$99:0:0:54:10:190:199:u26c29-07",
            "u6c35-07": "2:7:8:42:12:99:23:124:35$2:7:8:20:62:75:71:97:85$2:7:8:12:123:90:151:81:188$2:2:7:63:144:109:118:188:51",
            "u26c29-07": "1:0:0:18:29:187:29$1:0:0:73:10:73:48$1:0:0:132:10:132:48$1:12:13:44:59:44:87$1:2:2:44:59:163:59$1:22:23:163:59:163:87$1:2:2:44:87:163:87$1:0:0:32:116:176:116$1:0:0:21:137:190:137$7:32:7:102:59:102:123:102:176:10:190$2:7:0:105:137:126:169:181:182",
        },
        "name": "u6f22",
    },
    {
        # Nested buhin with stretch parameters (sx > 100, the two-segment mode).
        "id": "glyph:stretch",
        "buhin": {
            "outer": "99:150:0:10:10:190:190:inner:0:-10:50",
            "inner": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$2:7:8:60:60:120:100:160:160",
        },
        "name": "outer",
    },
    {
        # Transform ops (0:97/98/99) applied to already-drawn polygons.
        "id": "glyph:transform",
        "buhin": {
            "t97": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$0:97:0:0:0:200:200",
            "t98": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$0:98:0:0:0:200:200",
            "r90": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$0:99:1:0:0:200:200",
            "r180": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$0:99:2:0:0:200:200",
            "r270": "1:0:2:20:40:180:40$1:12:13:40:40:40:160$0:99:3:0:0:200:200",
        },
        "names": ["t97", "t98", "r90", "r180", "r270"],
    },
]


def glyph_cases():
    """→ [(id, buhin_dict, names)]; names is the list of glyph names to render."""
    return [
        (g["id"], g["buhin"], g["names"] if "names" in g else [g["name"]])
        for g in GLYPH_CASES
    ]


def build_cases():
    cases = []
    for shotai in ("m", "g"):
        for t in STROKE_TYPES:
            for gname, coords in GEOMETRIES.items():
                points = ":".join(str(c) for c in coords[:POINT_COUNT[t] * 2])
                for head in HEAD_TYPES:
                    for tail in TAIL_TYPES:
                        cases.append((f"{shotai}:{t}:{head}:{tail}:{gname}",
                                      f"{t}:{head}:{tail}:{points}",
                                      shotai, False, None, None))
        for t in (2, 4, 6, 7):
            for gname, coords in GEOMETRIES.items():
                points = ":".join(str(c) for c in coords[:POINT_COUNT[t] * 2])
                for head in (0, 7, 12, 22, 32):
                    for tail in (0, 2, 4, 7, 8, 13, 23):
                        cases.append((f"{shotai}c:{t}:{head}:{tail}:{gname}",
                                      f"{t}:{head}:{tail}:{points}",
                                      shotai, True, None, None))
    return cases


def load_golden() -> dict[str, str]:
    path = Path(__file__).parent / "fixtures" / "kurgm-strokes-golden.tsv"
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        case_id, _, fp = line.partition("\t")
        out[case_id] = fp
    return out
