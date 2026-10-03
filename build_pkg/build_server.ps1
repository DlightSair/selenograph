# Builds the self-contained registration service (no Python/torch needed to run it).
Set-Location "$PSScriptRoot\..\algo"
$dist = "$PSScriptRoot\dist"; $work = "$PSScriptRoot\work"
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --name selenograph-server `
  --paths src `
  --collect-all rasterio --collect-all pyproj --collect-submodules uvicorn --collect-submodules algo `
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.lifespan.on `
  --exclude-module onnxruntime --exclude-module torch --exclude-module kornia --exclude-module onnxruntime --exclude-module torchvision --exclude-module tensorboard --exclude-module IPython --exclude-module pytest `
  --distpath $dist --workpath $work --specpath $PSScriptRoot `
  src\algo\api\frozen_entry.py

