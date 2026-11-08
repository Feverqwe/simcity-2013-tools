package main

import (
	"bytes"
	"crypto/sha256"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
)

const property = 0x00b1b104
const ep1File = "SimCityDataEP1.package"
const sponsoredFile = "SimCity_DLC0.package"

var ep1LoaderID = resourceID{0x67771f5c, 0xa31e060f, 0x05afd67d}
var ep1ScriptLoad = regexp.MustCompile(`(?m)^simcity\.DynamicScriptLoader\.LoadScriptFromSrc\('[^'\r\n]+'\);[ \t]*\r?\n`)

const ep1BindingsMod = "000_Codex_EP1_Unbind.package"

var sponsoredIDs = []resourceID{
	{property, 0x53f0c900, 0xfb212a3c},                                     // Nissan
	{property, 0x56f0c900, 0x2ad521ba}, {property, 0x56f0c900, 0xd1c6c819}, // Crest
	{property, 0x56f0c900, 0xdae498c6}, {property, 0x56f0c900, 0xed2cd768},
	{property, 0x56f0c900, 0x51b708a9}, {property, 0x56f0c900, 0x3cfdeaba},
	{property, 0x56f0c900, 0x103bb38a}, {property, 0x56f0c900, 0x83559008},
	{property, 0x56f0c900, 0x59f58f96}, {property, 0x56f0c900, 0x83b7f016},
}

func build(dataDir string) (map[string][]byte, error) {
	ep1, err := readPackage(filepath.Join(dataDir, ep1File), func(id resourceID) bool {
		return id == ep1LoaderID || (id.kind == property && id.group&0xffff == 0xc900)
	})
	if err != nil {
		return nil, fmt.Errorf("%s: %w", ep1File, err)
	}
	loader := ep1[ep1LoaderID]
	if len(ep1ScriptLoad.FindAllIndex(loader, -1)) != 12 ||
		!bytes.Contains(loader, []byte("simcity.DLC_EP1.kResourceIDDLC_EP1")) {
		return nil, fmt.Errorf("unsupported Cities of Tomorrow UI loader")
	}
	unbound := ep1ScriptLoad.ReplaceAll(loader, nil)
	delete(ep1, ep1LoaderID)

	menu := make(resources)
	for id, original := range ep1 {
		updated, err := withoutCategory(original)
		if err != nil {
			return nil, err
		}
		if len(updated) != len(original) {
			menu[id] = updated
		}
	}
	if len(menu) == 0 {
		return nil, fmt.Errorf("no Cities of Tomorrow menu entries found")
	}

	sponsored, err := readPackage(filepath.Join(dataDir, sponsoredFile), func(id resourceID) bool {
		for _, candidate := range sponsoredIDs {
			if id == candidate {
				return true
			}
		}
		return false
	})
	if err != nil {
		return nil, fmt.Errorf("%s: %w", sponsoredFile, err)
	}
	if len(sponsored) != len(sponsoredIDs) {
		return nil, fmt.Errorf("some sponsored building entries are missing")
	}
	for id, original := range sponsored {
		updated, err := withoutCategory(original)
		if err != nil || len(updated) == len(original) {
			return nil, fmt.Errorf("cannot hide sponsored entry %08x", id.instance)
		}
		sponsored[id] = updated
	}

	intro, err := skipIntroPackage(dataDir)
	if err != nil {
		return nil, err
	}

	return map[string][]byte{
		startupMod:                        intro,
		"000_Codex_EP1_Menu_Test.package": writePackage(menu),
		ep1BindingsMod:                    writePackage(resources{ep1LoaderID: unbound}),
		sponsoredMod:                      writePackage(sponsored),
	}, nil
}

func requireClosed() error {
	if runtime.GOOS != "windows" {
		return nil
	}
	tasklist := filepath.Join(os.Getenv("SystemRoot"), "System32", "tasklist.exe")
	output, err := exec.Command(tasklist, "/FI", "IMAGENAME eq SimCity.exe", "/FO", "CSV", "/NH").Output()
	if err != nil {
		return fmt.Errorf("check whether SimCity is running: %w", err)
	}
	if bytes.Contains(bytes.ToLower(output), []byte(`"simcity.exe"`)) {
		return fmt.Errorf("close SimCity before changing mods")
	}
	return nil
}

type change struct {
	path, staged string
	original     []byte
	remove       bool
}

const startupMod = "000_Codex_Skip_Intro.package"
const legacyStartupHash = "af033cb4eae9ec6c43a59c3439499544c5de1e0dcd5743e8546231d3d5b1dbd3"
const legacyLogoHash = "37cc97ee766ade2d1690a855045977893275e5e60f2fbf0995ea8f1746abf5f3"
const sponsoredMod = "000_Codex_Sponsored_Buildings.package"
const legacySponsoredHash = "b8371e6c0cd36568328975bebbbb78090998ba03ac0dd7b5b63f62ef76307cda"

func apply(dataDir string, packages map[string][]byte, remove bool) error {
	if err := requireClosed(); err != nil {
		return err
	}
	var changes []change
	for _, name := range sortedNames(packages) {
		path := filepath.Join(dataDir, name)
		content, err := os.ReadFile(path)
		switch {
		case err == nil:
			hash := fmt.Sprintf("%x", sha256.Sum256(content))
			legacy := (name == sponsoredMod && hash == legacySponsoredHash) ||
				(name == startupMod && (hash == legacyStartupHash || hash == legacyLogoHash))
			if !legacy && !bytes.Equal(content, packages[name]) {
				return fmt.Errorf("existing file differs from this mod: %s", path)
			}
			if remove || legacy {
				changes = append(changes, change{path: path, original: content, remove: true})
			}
			if legacy && !remove {
				changes = append(changes, change{path: path})
			}
		case errors.Is(err, os.ErrNotExist):
			if !remove {
				changes = append(changes, change{path: path})
			}
		default:
			return err
		}
	}
	for _, legacy := range []struct{ name, hash string }{
		{"000_Codex_EP1_No_Balloons.package", "3e09454954aa2a06a95d5a490c0f330df9e45951c5a9d6cab6f8897021fe1762"},
		{"000_Codex_EP1_Unbind_Test.package", "524ee1773176bf0a12fda51c53011fe2846ecd9dc0496aa8661e565705acf3dc"},
		{filepath.Join("Locale", "ru-ru", "000_Codex_EP1_Russian_Thoughts.package"), "0abd2b4f2d9b1108253776a03c89e1f7e036101bf1e62bb71098adfde61d7d69"},
	} {
		path := filepath.Join(dataDir, legacy.name)
		old, err := os.ReadFile(path)
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		if err == nil && fmt.Sprintf("%x", sha256.Sum256(old)) == legacy.hash {
			changes = append(changes, change{path: path, original: old, remove: true})
		}
	}
	if len(changes) == 0 {
		fmt.Println("No changes needed.")
		return nil
	}
	stage, err := os.MkdirTemp(dataDir, ".simcity-cleanup-")
	if err != nil {
		return err
	}
	cleanup := true
	defer func() {
		if cleanup {
			os.RemoveAll(stage)
		}
	}()
	for i := range changes {
		item := &changes[i]
		item.staged = filepath.Join(stage, fmt.Sprintf("%d.package", i))
		if !item.remove {
			if err := os.WriteFile(item.staged, packages[filepath.Base(item.path)], 0644); err != nil {
				return err
			}
		}
	}
	if err := requireClosed(); err != nil {
		return err
	}
	for i, item := range changes {
		if err := item.apply(); err != nil {
			for j := i - 1; j >= 0; j-- {
				if rollbackErr := changes[j].rollback(); rollbackErr != nil {
					cleanup = false
					err = errors.Join(err, fmt.Errorf("rollback %s: %w", changes[j].path, rollbackErr))
				}
			}
			if !cleanup {
				err = fmt.Errorf("%w; staged files are in %s", err, stage)
			}
			return err
		}
	}
	for _, item := range changes {
		action := "Installed"
		if item.remove {
			action = "Removed"
		}
		fmt.Printf("%s %s\n", action, filepath.Base(item.path))
	}
	return nil
}

func (item change) apply() error {
	if item.remove {
		current, err := os.ReadFile(item.path)
		if err != nil {
			return err
		}
		if !bytes.Equal(current, item.original) {
			return fmt.Errorf("file changed while preparing to remove it: %s", item.path)
		}
		return os.Rename(item.path, item.staged)
	}
	// A hard link publishes the complete staged file without overwriting an existing file.
	return os.Link(item.staged, item.path)
}

func (item change) rollback() error {
	if item.remove {
		return os.Link(item.staged, item.path)
	}
	current, err := os.Stat(item.path)
	if err != nil {
		return err
	}
	original, err := os.Stat(item.staged)
	if err != nil {
		return err
	}
	if !os.SameFile(current, original) {
		return fmt.Errorf("file changed during installation")
	}
	return os.Remove(item.path)
}

func sortedNames(packages map[string][]byte) []string {
	names := make([]string, 0, len(packages))
	for name := range packages {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func run(args []string) error {
	flags := flag.NewFlagSet("simcity-2013-tools", flag.ContinueOnError)
	check := flags.Bool("check", false, "build in memory and print checksums")
	remove := flags.Bool("remove", false, "remove matching generated mods")
	var scale byte
	flags.Func("ui-scale", "set the Windows UI scale (1, 2, or 3)", func(value string) error {
		if value != "1" && value != "2" && value != "3" {
			return fmt.Errorf("choose 1, 2, or 3")
		}
		scale = value[0]
		return nil
	})
	flags.Usage = func() {
		fmt.Fprintln(flags.Output(), "Usage: simcity-2013-tools-windows-amd64.exe [-check | -remove] <SimCity directory>")
		fmt.Fprintln(flags.Output(), "       simcity-2013-tools-windows-amd64.exe -ui-scale <1|2|3>")
		flags.PrintDefaults()
	}
	if err := flags.Parse(args); err != nil {
		return err
	}
	if scale != 0 {
		if flags.NArg() != 0 || *check || *remove {
			return fmt.Errorf("-ui-scale is a separate command and takes no game path")
		}
		return setUIScale(scale)
	}
	if flags.NArg() != 1 || (*check && *remove) {
		flags.Usage()
		return fmt.Errorf("provide the SimCity directory and at most one mode")
	}
	dataDir := filepath.Join(flags.Arg(0), "SimCityData")
	packages, err := build(dataDir)
	if err != nil {
		return err
	}
	if *check {
		for _, name := range sortedNames(packages) {
			fmt.Printf("%x  %s\n", sha256.Sum256(packages[name]), name)
		}
		return nil
	}
	return apply(dataDir, packages, *remove)
}

func main() {
	if err := run(os.Args[1:]); err != nil && !errors.Is(err, flag.ErrHelp) {
		fmt.Fprintln(os.Stderr, "SimCity 2013 Tools:", err)
		os.Exit(1)
	}
}
