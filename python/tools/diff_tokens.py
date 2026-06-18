import json
from pathlib import Path
import os

HERE = Path(__file__).resolve().parent
PY_ROOT = HERE.parent
REPO = PY_ROOT.parent
KT_GOLDEN_DIR = REPO / "zpa-core" / "build" / "goldens" / "tokens"
PY_GOLDEN_DIR = PY_ROOT / "build" / "tokens"

def compare_json_files():
    token_files = PY_GOLDEN_DIR.rglob("*.json")
    for file in token_files:
        kt_file = KT_GOLDEN_DIR / file.name
        if not os.path.exists(kt_file):
            continue

        with open(file) as f: py = json.load(f)
        with open(kt_file) as f: kt = json.load(f)

        print(f"{file.name} --> {py == kt}")

if __name__ == "__main__":
    compare_json_files()

