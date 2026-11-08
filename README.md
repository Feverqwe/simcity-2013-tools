# SimCity 2013 Tools

This repository contains SimCity Cleanup for game tweaks and an optional HD texture builder for the interface.

## SimCity Cleanup

SimCity Cleanup installs four mods for SimCity (2013). They hide Cities of Tomorrow and sponsored buildings from the build menu, disable the expansion's UI scripts, and skip the startup movie. The main menu shows the base-game logo and loading screens use base-game tips. The expansion's simulation remains installed. The tool builds the mods from your installed game files. It supports the EA app version with Cities of Tomorrow installed.

Download `simcity-cleanup-windows-amd64.exe` from [Releases](https://github.com/Feverqwe/simcity-2013-tools/releases). The executable runs on 64-bit Windows and requires no additional runtime.

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

## UI scaling on 4K displays

Close SimCity and run:

```powershell
.\simcity-cleanup-windows-amd64.exe -ui-scale 2
```

Use `1` for the default scale or `3` for a larger interface. This command uses the current Windows user's preferences and saves a backup beside `Preferences.prop` before changing it. If the preferences file is missing, start SimCity once and close it.

## Black screen at launch

On the tested EA app installation, launching SimCity with `-noUpdates` produced a black screen. Remove that argument from the EA app's advanced launch options if you added it. The startup movie patch works with the normal EA app launch.

## HD interface textures

The optional IllustrationJaNai builder generates 2× UI textures from your installed game files. Download the builder ZIP from the release and follow the [Windows setup and installation guide](ui-hd/README.md).

To build the cleanup executable locally, run `go build .` from the repository root. Pushing a version tag publishes the Windows executable and texture builder source archive in a GitHub Release.
