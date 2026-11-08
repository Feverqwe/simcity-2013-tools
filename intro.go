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
	const ep1Logo = `1==simcity.cLauncher3D.mHasEPO?(b.FindControlByID(this.mControlIds.LOGO).SetWindowImage("Graphics/Common/Graphics/SimCity_Logo_COT.png"),` +
		"\r\n" +
		`b.FindControlByID(this.mControlIds.LOGO_BG).SetVisibility(!0),b.FindControlByID(this.mControlIds.LOGO_EP).SetVisibility(!0),b.FindControlByID(this.mControlIds.LOGO_FT).SetVisibility(!1)):`
	if bytes.Count(source, []byte(ep1Logo)) != 1 {
		return nil, fmt.Errorf("%s: unsupported main menu logo handler", appPackage)
	}
	source = bytes.Replace(source, []byte(original), []byte(replacement), 1)
	const ep1Tips = `if(simcity.gGlobalUIHandler&&1==simcity.gGlobalUIHandler.mHasEp||simcity.cLauncher3D&&1==simcity.cLauncher3D.mHasEPO)a.push(["EP1LoadingTips","tip"]),a.push(["EP1LoadingScreen","quip"]);`
	if bytes.Count(source, []byte(ep1Tips)) != 1 {
		return nil, fmt.Errorf("%s: unsupported loading tips handler", appPackage)
	}
	source = bytes.Replace(source, []byte(ep1Logo), nil, 1)
	entries[id] = bytes.Replace(source, []byte(ep1Tips), nil, 1)
	return writePackage(entries), nil
}
