# SimCity (2013) UI texture builder

Build a SimCity UI texture mod from your own PC installation. The builder uses IllustrationJaNai V3detail HAT-L at 4× and outputs textures at 2×. It covers the UI images in the included manifest, such as icons, portraits, previews, and launcher backgrounds. The archive contains the builder and resource manifest. Download the model weights separately.

## Set up on Windows

Install [64-bit Python 3.12](https://www.python.org/downloads/) and open PowerShell in the extracted builder folder. For an NVIDIA GPU, install a current driver.

Create a virtual environment and install PyTorch and the builder dependencies:

```powershell
py -3.12 -m venv .venv
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
& $python -m pip install -r requirements.txt
& $python -c "import torch; print(torch.cuda.is_available())"
```

For a different CUDA build, use the Windows/Pip command from the [PyTorch installer](https://pytorch.org/get-started/locally/) with `& $python -m pip`. For CPU-only generation, use `https://download.pytorch.org/whl/cpu` as the index and pass `--device cpu` when building. A full CPU build can take substantially longer.

## Build the package

Download [IllustrationJaNai_V3detail.zip](https://github.com/the-database/MangaJaNai/releases/download/3.0.0/IllustrationJaNai_V3detail.zip) into the builder folder. Keep it as a ZIP file.

Replace the example path with the directory that contains your game's `SimCityData` folder:

```powershell
$game = 'D:\EA\SimCity'
& $python .\build.py --game $game --device cuda
```

Wait for the `Built ... overrides` message. A full build took roughly 40 minutes on an RTX 5070 Ti. If interrupted, rerun the same command from the same folder to reuse generated textures.

For a quick test before the full build, run:

```powershell
& $python .\build.py --game $game --device cuda --match Advisor_Male_Roads.png --output IllustrationJaNai-preview.package
```

## Install and remove

Close SimCity. Copy the completed full package into the game's `SimCityData` folder:

```powershell
$mod = '000_Codex_UI_IllustrationJaNai.package'
$target = Join-Path (Join-Path $game 'SimCityData') $mod
[System.IO.File]::Copy((Join-Path (Get-Location).Path $mod), $target, $false)
```

Launch SimCity normally. To uninstall, close the game and remove `000_Codex_UI_IllustrationJaNai.package` from `SimCityData`. SimCity will read its original textures again.

The builder requires the resource packages of SimCity (2013) covered by the manifest. If it reports a missing package or resource, check that the game path is correct and the installation is complete.
