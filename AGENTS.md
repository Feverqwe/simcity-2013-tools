# AGENTS.md

Agent handoff for SimCity 2013 Tools. Start with the navigation table and read only the relevant sections. The public usage contract lives in [README.md](README.md) and [ui-hd/README.md](ui-hd/README.md). Keep this file focused on context that would otherwise have to be rediscovered.

## Navigation

| Task | Start here |
| --- | --- |
| Cleanup options, patch application, or rollback | [main.go](main.go), [dbpf.go](dbpf.go) |
| Intro or black screen at launch | [intro.go](intro.go), [Launch and visual debugging](#launch-and-visual-debugging) |
| 4K interface scale | [preferences.go](preferences.go) |
| HD UI, AI weights, or texture seams | [ui-hd/build.py](ui-hd/build.py), [ui-hd/ui-manifest.json](ui-hd/ui-manifest.json), [HD interface](#hd-interface) |
| World texture formats, grouping, or archive precedence | [ui-hd/world.py](ui-hd/world.py), [HD world](#hd-world) |
| Interrupted install or uninstall | [ui-hd/install-world.py](ui-hd/install-world.py), [Verification](#verification) |
| Prior experiments, test evidence, and unfinished work | [Engineering memory](docs/agent-memory.md) |
| Releases and deliverables | [.github/workflows/release.yml](.github/workflows/release.yml), [Repository and releases](#repository-and-releases) |

## Repository and releases

- GitHub repository is `Feverqwe/simcity-2013-tools`. The established local checkout may still be named `simcity-cleanup` after the repository rename. Check `git remote -v` and `git status --short --branch` before choosing a checkout.
- Commit only on explicit request. Preserve unrelated changes. Push and tag only when requested. Check the latest tags and release status rather than relying on a remembered version.
- A `v*` tag triggers the Windows release workflow. It publishes the Go executable and `simcity-ui-hd-builder.zip`, which contains the source for both HD modes. The Go executable handles cleanup and settings. The Python builder generates texture mods locally.
- Keep original and generated game assets, model weights, caches, galleries, host connection details, and local test paths out of Git and release archives.
- History anchors: `817f320` introduced the staged World builder and the final thought-bubble manifest exclusions. `d26bbe0` added recovery from partially applied World changes and was released as `v1.3.1`.

## HD interface

- UI and World use IllustrationJaNai V3detail HAT-L. The model runs at 4× and the delivered textures are 2×. The UI manifest controls what is replaced.
- Known regressions: upscaling UI slices independently caused seams in thought bubbles and some window and button textures. Earlier fixes are in `547e7d6` and `839697e`. `817f320` also excluded the remaining thought-bubble variants, overlays, and tails. Check the manifest history before reintroducing any of these textures.
- Keep a repeatable UI test small with `build.py ui --match` and a separate output filename. Check actual in-game rendering at the same UI scale, especially bubbles and dialogs that stretch across several texture pieces.

## HD world

- Use `build.py world --help` and `install-world.py --help` for the current set names. The sets reflect the order used in development: ordinary RW4, L8, decals, remaining Raster, six-face textures, and duplicate IDs. Independent sets must not install overlapping resource keys.
- RW4 can contain several texture sections within one resource. Keep its non-texture sections and original mip levels intact. In tested six-face containers the blob has one complete mip chain per face. Some faces are separate terrain materials packed together, so do not assume every such resource is an environment reflection.
- Raster can store decals, material maps, or masks. A colored thumbnail alone does not establish how a shader uses its channels. Decal classification uses game dictionaries. Keep alpha and channel semantics in mind when changing the model or the encoder.
- An identical resource ID can refer to different data in different archives. The duplicate-ID set updates each version in its original archive under its original name. A single overlay would force one variant to win. Preserve archive names, index order, and reversible backups.
- Open review finding from `817f320`: the builder discovers DBPF index offsets before it copies the source archive for patching. An external update between those operations could make offsets stale. If fixing this, read and patch a consistent snapshot, then verify the generated archive by re-reading its resource IDs. The interrupted-install fix in `d26bbe0` did not address this finding.

## Launch and visual debugging

- Test with the normal EA app launch. `-noUpdates` produced a black screen on the tested installation. The intro-skip package and the built-in Single Player mode are separate mechanisms.
- Intermittent menu loading also occurred during testing. The available EA logs did not establish an authentication cause. When isolating a launch issue, keep the game mode and installed sets constant and change one variable per test.
- Compare visual effects at the same camera position, zoom, and time of day. Flashing lights need comparison across their animation cycle. Close the game before changing packages. When disabling World completely, restore archives modified by the duplicate-ID set as well as removing the overlay sets.

## Verification

- Go changes: run `go vet ./...` and check the relevant command or build. Python changes: check both CLI entry points and exercise the affected behavior. Run `git diff --check` before handing off.
- World changes: build from copies of clean game archives. Check dimensions, resource IDs, mip preservation, and that similarly keyed variants remain different in their respective archives. Test in-game effects on the Windows runner separately from structural checks.
- Installer changes: exercise staged installation and removal. Interrupt between two archive replacements, then test both retry and rollback from the resulting mixed state. Verify restored originals with SHA-256 and confirm unrelated sets stay installed. Reject unfamiliar archive bytes without overwriting them.
- Record new reproducible findings in the [engineering memory](docs/agent-memory.md) if they are likely to matter in later sessions. Keep temporary logs, screenshots, and machine-specific details in local scratch space.
