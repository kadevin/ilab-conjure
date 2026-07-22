# iLab CONJURE macOS Standard App package

Use the DMG package for new installs. Drag iLab GPT CONJURE.app to Applications,
then launch it from Finder or Spotlight.

This app stores user data in:

```text
~/Library/Application Support/iLab GPT CONJURE
```

On first launch, the app can detect adjacent legacy portable data and asks
before copying it into the standard app data directory. Migration copies portable
data only; it does not move or delete the old `data/` folder, and it will not
overwrite an existing standard data directory.

The app is not notarized. If Gatekeeper blocks first launch, right-click
or Control-click iLab GPT CONJURE.app, choose Open, and confirm the system
prompt.

The standard app checks the signed update manifest. Versions that bundle the
standard updater show `Install Update`: after you confirm, the app downloads and
SHA256-verifies the matching DMG, quits, automatically replaces the installed
app with rollback protection, and relaunches. Data in Application Support is not
part of the app replacement.

The first version that includes this updater must still be installed manually
over an older app. If the bundled helper is missing, `Check for Updates` safely
falls back to opening the matching DMG download. Updates are user-confirmed, not
silent background installs.
