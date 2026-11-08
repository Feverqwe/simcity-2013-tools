# SimCity Cleanup

This script installs three mods for SimCity (2013). They hide Cities of Tomorrow buildings and sponsored buildings from Nissan, Crest, and Progressive in the build menu, and disable Cities of Tomorrow speech and thought bubbles. The script builds the mods from your installed game files. It was tested with the EA app version of SimCity with Cities of Tomorrow installed.

Requires Python 3.9 or later. Close SimCity, open PowerShell in this folder, and run the following command with your installation path.

```powershell
py -3 .\simcity_cleanup.py 'D:\EA\SimCity'
```

Add `--check` to build and verify the packages without installing them. Add `--remove` to uninstall the mods. The installer also removes the earlier Russian text override if it matches the original experimental file.

Buildings already placed can remain on the map. Use a new city to check the build menu and resident bubbles.
