# SimCity (2013) HD texture builder

Build separate UI and 3D world texture mods from your own SimCity installation. Both use IllustrationJaNai V3detail HAT-L and produce 2× textures. Download the model weights separately.

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

## Build the UI package

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

## Install and remove the UI package

Close SimCity. Copy the completed full package into the game's `SimCityData` folder:

```powershell
$mod = '000_Codex_UI_IllustrationJaNai.package'
$target = Join-Path (Join-Path $game 'SimCityData') $mod
[System.IO.File]::Copy((Join-Path (Get-Location).Path $mod), $target, $false)
```

Launch SimCity normally. To uninstall, close the game and remove `000_Codex_UI_IllustrationJaNai.package` from `SimCityData`. SimCity will read its original textures again.

The builder requires the resource packages of SimCity (2013) covered by the manifest. If it reports a missing package or resource, check that the game path is correct and the installation is complete.

## Build the World mod

Use the same environment, model weights and game path as for the UI builder. Start from an installation with its original SimCity archives. The World build takes longer and needs several gigabytes of free disk space for the cache and output.

```powershell
& $python .\build.py world --game $game --device cuda --output .\world-hd
```

If interrupted, rerun the command to reuse cached textures. Keep the build folder for installation and rollback.

Use `--sets` to build only the sets you want to test. Run `build.py --help` to list the available names. Omit `--sets` to build every set.

```powershell
& $python .\build.py world --game $game --device cuda --output .\world-hd-small --sets rw4 l8
```

## Install and remove the World mod

Close SimCity before either command. The installer backs up any original archives it needs to update and keeps resources with matching IDs in their respective archives. Use the same build folder for both commands.

```powershell
& $python .\install-world.py install --game $game --build .\world-hd
& $python .\install-world.py uninstall --game $game --build .\world-hd
```

Omit `--sets` to change every set in the build folder. For a staged test, use the same build folder and name the sets you want to install or remove:

```powershell
& $python .\install-world.py install --game $game --build .\world-hd --sets rw4
& $python .\install-world.py install --game $game --build .\world-hd --sets l8 decals
& $python .\install-world.py uninstall --game $game --build .\world-hd --sets decals
```

UI and World can be installed or removed independently.
