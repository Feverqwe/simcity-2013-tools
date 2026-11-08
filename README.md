# SimCity Cleanup

SimCity Cleanup installs three mods for SimCity (2013). They hide Cities of Tomorrow buildings and sponsored buildings from Nissan, Crest, and Progressive in the build menu, and disable Cities of Tomorrow speech and thought bubbles. The tool builds the mods from your installed game files. It supports the EA app version with Cities of Tomorrow installed.

Download `simcity-cleanup-windows-amd64.exe` from [Releases](https://github.com/Feverqwe/simcity-cleanup/releases). The executable runs on 64-bit Windows and requires no additional runtime.

Close SimCity, open PowerShell in the folder containing the download, and run the command with your game's installation path.

```powershell
.\simcity-cleanup-windows-amd64.exe 'D:\EA\SimCity'
```

Use `-check` before the path to preview the generated package checksums. Use `-remove` before the path to uninstall the mods.

```powershell
.\simcity-cleanup-windows-amd64.exe -check 'D:\EA\SimCity'
.\simcity-cleanup-windows-amd64.exe -remove 'D:\EA\SimCity'
```

Buildings already placed can remain on the map. Use a new city to check the build menu and resident bubbles.

To build locally, run `go build .` from the repository root. Pushing a version tag such as `v1.0.0` triggers the Windows build and publishes the executable in a GitHub Release.
