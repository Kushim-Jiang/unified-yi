import json
from pathlib import Path

data_dir = Path(__file__).parent.parent / "data"


def to_json(file: Path):
    with file.open(encoding="utf-8") as f:
        lines = f.readlines()[1:]

    res = []
    for line in lines:
        glyf, src, pron, mean = line.strip().split("\t")
        res.append({"glyf": glyf, "src": src, "pron": pron, "mean": mean})

    if not (data_dir.parent / "temp").exists():
        (data_dir.parent / "temp").mkdir()
    with open("temp/" + file.stem + ".json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


for tsv_file in data_dir.iterdir():
    to_json(tsv_file)
