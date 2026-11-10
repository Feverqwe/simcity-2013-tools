# Engineering memory

This is a historical handoff for agents working on SimCity 2013 Tools. Use [AGENTS.md](../AGENTS.md) to find the code and public docs. Counts and observations below describe the tested EA app installation, which included Cities of Tomorrow. Use the current build output to measure another installation.

## Cleanup and launch

| Change | Evidence or reason to revisit |
| --- | --- |
| Go cleanup and Windows releases | `41ad88d` ported the installer. `9c5a2fc` switched the release workflow to stable Go. The release ships one executable for cleanup and a separate Python source ZIP for HD textures. |
| Sponsored build menu | `71b4180` corrected overlap between sponsored and expansion overrides. Review source resource IDs and ownership in `main.go` before changing the packages. Existing placed buildings are a separate case from available build-menu entries. |
| Cities of Tomorrow | `1eb3e2f` disabled the expansion UI loader bindings and restored the base-game logo and loading tips. Earlier attempts to remove or hollow out the expansion archive led to stuck startup or menus. Keep the expansion installed for the supported cleanup path. Removing text and replacing the remaining futuristic menu backdrop were dropped during testing. |
| Intro | The startup package sets `SkipIntroMovie`. Normal launch worked with it. The separate `-noUpdates` argument produced a black screen and was left out. |
| UI scale | `a1cf6ea` added `-ui-scale`. It changes the current Windows user's preferences and backs up the original. Validate scale and image sharpness separately. A larger control can still use a low-resolution image. |

The Go installer generates overrides from the user's game archives. Its compatibility handling is tied to known hashes. Preserve the distinction between a known old generated file and an unrelated mod when changing install or removal.

Intermittent menu loading occurred before and after texture experiments. EA logs did not establish a login error or ban. The built-in Single Player mode and EA app offline mode are separate controls. No forced-offline SimCity launch flag was verified. For diagnostics, first reproduce with the same installed packages, then vary online/offline or one package set. Treat an unskippable movie or persistent spinner as a symptom.

## HD UI decisions

- Candidate comparisons covered AoMR, HDCube, AnimeSharp V3, TextureDAT2, RGT-S and IllustrationJaNai. The winner varied by image. AoMR often preserved fine detail but could add stair steps. TextureDAT2 often smoothed outlines at the cost of detail. Contrast and sharpness scores alone disagreed with visual inspection. IllustrationJaNai was chosen for the shipped pipeline after checking details in portraits, small shadows and larger artwork. No automatic model ranking ships.
- The first usable in-game result came from generating replacement PNG/JPEG resources and installing a separate overlay. The Python implementation was kept for model inference. A Go/ONNX port was considered and dropped. There is no current Go `ui-hd` command.
- Regression examples: green and red resident thought bubbles showed rectangular joins when their parts were independently upscaled. `547e7d6` restored stretch slices. `839697e` restored other window and button slices. `817f320` also removed remaining thought-bubble variants, overlays and tails from the HD manifest. A missing center shadow in the quit dialog was treated as an apparent base-game rendering issue, without a confirmed asset-level diagnosis.
- Good visual probes: zoning toolbar at 4K, advisor portraits, launcher background, wide thought bubbles, and dialog headers. Compare at the same UI scale. Gallery images must come from actual source and model output. A plain resize is only a diagnostic baseline.

## HD World decisions

The early exporter mapped RW4 and Raster resources to PNGs. Its 2× previews used ordinary interpolation. Those results established decoding and dimensions. The shipped World RGB output uses IllustrationJaNai. L8 was first tested with nearest-neighbor scaling and later with IllustrationJaNai in its own package.

The overnight model run finished 4,691 unique PNGs corresponding to 5,639 initial inventory rows. It took about 2 h 56 min on an RTX 5070 Ti in WSL. Initial estimates based on small early textures were too optimistic. That run represented only one face per detected cube container. All six faces were processed separately afterward.

| Set | Final builder resources on the tested installation | Notes |
| --- | ---: | --- |
| `rw4` | 2,489 | Contains one or more texture sections per resource. DXT1 alpha coverage was checked after encoding. |
| `l8` | 268 | One-channel textures. Keep the original mip chain. |
| `decals` | 1,210 | Classified through decal dictionary references. Check signs and graffiti up close. |
| `raster` | 1,031 | Other Raster resources. Check terrain, lot boundaries, and lighting for channel or mask artifacts. |
| `cubemaps` | 26 | 156 faces. Some containers hold terrain materials in separate faces. Preserve one mip chain per face and their order. |
| `conflicts` | 6 | Four updated RW4 resources in Graphics and two distinct Raster versions in Game and DLC0. |

The final build count was 5,030 **resources**. Inventory rows, unique PNGs, texture sections, faces and DBPF resources are different units. Small or unsupported textures were left in place. The early report grouped these together. Codes `0x32` and `0x74` are L8 and four-channel float respectively. A side of four pixels or fewer was only a heuristic for potential lookup data. Some of the narrow resources are palettes or material parameters, so a visual upscale is not necessarily valid.

### Archive order and test state

- Four RW4 IDs occur in both Graphics and DLC0. Their DLC0 versions contain small resources retained as originals. One Raster ID, `c468685a`, has distinct supported images in Game and DLC0. Choosing one version in a shared overlay would change archive precedence. The final approach keeps each version in its original archive under its original name.
- The live runner was tested with incremental experimental packages and archive copies. A later release-style build produced all six sets from copies of the original archives. A separate install/rollback test applied `decals`, then `conflicts`, and verified that rollback restored original archive SHA-256 values without removing decals. Do not assume the live runner uses the release installer's filenames or backup suffix.
- The user confirmed play with the early World sets, tested the red lights with World disabled, and asked to re-enable it. The lights were not established as a texture regression. After the final cube and duplicate-ID changes, intermittent menu loading was still discussed and the user chose to keep the build. No repeatable authentication cause or isolated final-set failure was established.
- For future comparisons, disable only the suspect set first. A complete comparison with vanilla World also requires restoring modified stock archives. Keep the HD UI state consistent between screenshots.

## Regression checks and outstanding work

- `v1.3.0` shipped the staged builder. Review reproduced a broken mixed install after interruption and after an EA repair restored only some archives. `d26bbe0` and `v1.3.1` fixed recovery. Tests covered resume, rollback, repeated commands, and refusal to overwrite unknown archive versions.
- Still open: World build can retain a DBPF index offset collected before an external archive change. The later checksum compares the copy with a more recent source and cannot prove it matches the earlier index. Reproduce with a controlled change to a scratch archive between scan and copy. A fix should read and patch one consistent snapshot, and re-read the generated entries to prove the intended resources changed.
- The original Windows game was used for visual tests. The release-style World build and installer checks ran against archive copies in WSL. Re-test Windows process checks, file replacement and recovery if modifying platform-specific installer code.
- Prior scratch artifact names, if the original workspace is available: `check-recovery.py` reproduces interruption, `check-sets.sh` checks selected sets and SHA-256 rollback, and `simcity-world-gallery/ai-pilot.html` compares original with model output. The gallery's adjacent PNGs were blocked by a sandboxed `file://` viewer. It worked when served over local HTTP. The user requested separate PNGs rather than embedding them.
