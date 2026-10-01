"""Download the LoFTR 'outdoor' checkpoint into algo/models/.

kornia.feature.LoFTR(pretrained="outdoor") hardcodes a dead academic HTTP
host (cmp.felk.cvut.cz) for this download, so we fetch the same checkpoint
from the official kornia HuggingFace org instead.
"""

import urllib.request
from pathlib import Path

URL = "https://huggingface.co/kornia/loftr/resolve/main/loftr_outdoor.ckpt"
OUT_PATH = Path(__file__).parents[1] / "models" / "loftr_outdoor.ckpt"

if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {URL} -> {OUT_PATH}")
    urllib.request.urlretrieve(URL, OUT_PATH)
    print(f"done, {OUT_PATH.stat().st_size} bytes")
