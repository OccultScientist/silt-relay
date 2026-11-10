"""Stage the static reader and a pinned browser Python runtime for GitHub Pages."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import shutil
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
RUNTIME = "https://cdn.jsdelivr.net/pyodide/v314.0.0/full/"
ASSETS = {
    "pyodide.mjs": "3abfa8bfc2d1dc9d733f4b0b5c3b35bb469295e455abf13f5c0fac70a1c2e961",
    "pyodide.asm.mjs": "7808c4d7a9fee23a02b0c8b7bbd51b1358e8d41bbe89e5c0ee9c0c4db7b9328f",
    "pyodide.asm.wasm": "4d23bd074cc536a96660c9168e223e3aaf01944096ad829737a9c87fec4b28eb",
    "pyodide-lock.json": "f545248ab161ead36adf7110a358334974e97b08f40c7219e97077d380f7247b",
    "python_stdlib.zip": "1215cd239a270c13a3ecb1a84c84b7b3241baf7ea7f54615f00d79ff69c82787",
}


def runtime_asset(name):
    output = SITE / "runtime" / name
    expected = ASSETS[name]
    if output.is_file() and sha256(output.read_bytes()).hexdigest() == expected:
        return
    with urlopen(RUNTIME + name, timeout=45) as response:
        data = response.read()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Checksum mismatch for {name}")
    output.write_bytes(data)


def main():
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "runtime").mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=len(ASSETS)) as executor:
        list(executor.map(runtime_asset, ASSETS))

    for source in (ROOT / "web").iterdir():
        if source.is_file():
            shutil.copyfile(source, SITE / source.name)
    for source in (ROOT / "web" / "runtime").iterdir():
        shutil.copyfile(source, SITE / "runtime" / source.name)
    for path in ("silt_relay.py", "data/releases.json", "data/vectors.tsv", "data/VECTORS.md"):
        shutil.copyfile(ROOT / path, SITE / path)
    (SITE / ".nojekyll").touch()
    print(SITE)


if __name__ == "__main__":
    main()
