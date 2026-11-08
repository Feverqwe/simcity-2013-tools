package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
)

var uiZoomLine = regexp.MustCompile(`(?m)^OptionUIZoomLevel[ \t]+([123])[ \t]*\r?$`)

func setUIScale(scale byte) error {
	appData := os.Getenv("APPDATA")
	if !filepath.IsAbs(appData) {
		return fmt.Errorf("APPDATA does not point to a Windows user profile")
	}
	if err := requireClosed(); err != nil {
		return err
	}
	path := filepath.Join(appData, "SimCity", "Preferences", "Preferences.prop")
	original, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("preferences not found at %s; start SimCity once and close it", path)
	}
	if err != nil {
		return err
	}
	matches := uiZoomLine.FindAllSubmatchIndex(original, 2)
	if len(matches) != 1 {
		return fmt.Errorf("expected one valid OptionUIZoomLevel in %s", path)
	}
	position := matches[0][2]
	if original[position] == scale {
		fmt.Printf("UI scale is already %c.\n", scale)
		return nil
	}

	updated := bytes.Clone(original)
	updated[position] = scale
	stage, err := writeSibling(path, ".new-", updated)
	if err != nil {
		return err
	}
	defer os.Remove(stage)
	if err := requireClosed(); err != nil {
		return err
	}
	current, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if !bytes.Equal(current, original) {
		return fmt.Errorf("preferences changed while preparing the update")
	}
	backup, err := writeSibling(path, ".before-ui-scale-", original)
	if err != nil {
		return err
	}
	if err := os.Rename(stage, path); err != nil {
		return fmt.Errorf("update preferences: %w; backup: %s", err, backup)
	}
	fmt.Printf("UI scale set to %c. Backup: %s\n", scale, backup)
	return nil
}

func writeSibling(path, suffix string, data []byte) (string, error) {
	file, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+suffix+"*")
	if err != nil {
		return "", err
	}
	_, writeErr := file.Write(data)
	if err := errors.Join(writeErr, file.Close()); err != nil {
		os.Remove(file.Name())
		return "", err
	}
	return file.Name(), nil
}
