package main

import (
	"bytes"
	"fmt"
	"path/filepath"
)

func skipIntroPackage(dataDir string) ([]byte, error) {
	const appPackage = "SimCity_App.package"
	id := resourceID{0x67771f5c, 0x40464200, 0x696447ea}
	entries, err := readPackage(filepath.Join(dataDir, appPackage), func(candidate resourceID) bool {
		return candidate == id
	})
	if err != nil {
		return nil, fmt.Errorf("%s: %w", appPackage, err)
	}
	source := entries[id]
	const original = `simcity.cCurtainUIHandler.prototype.Show=function(){!0==simcity.cLauncher3D.mSkipIntroMovie&&simcity.gSessionManager.SetSkipMovie(!0);var a=simcity.gSessionManager.mSkipMovie;!1==a||"false"==a?(this.PlayIntroMovie(),simcity.gSessionManager.SetSkipMovie(!0)):this.OnIntroMovieStop()};`
	const replacement = `simcity.cCurtainUIHandler.prototype.Show=function(){simcity.gSessionManager.SetSkipMovie(!0);this.OnIntroMovieStop()};`
	if bytes.Count(source, []byte(original)) != 1 {
		return nil, fmt.Errorf("%s: unsupported intro handler", appPackage)
	}
	entries[id] = bytes.Replace(source, []byte(original), []byte(replacement), 1)
	return writePackage(entries), nil
}
