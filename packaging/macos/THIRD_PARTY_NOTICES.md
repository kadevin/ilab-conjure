# Third-Party Notices

This portable package contains iLab CONJURE, Python.org CPython for macOS,
Python packages installed from `requirements-webui.txt`, and a prebuilt WebUI
JavaScript bundle that includes frontend npm packages from `package-lock.json`.

## CPython

The bundled Python runtime is distributed by the Python Software Foundation.
See the Python license documentation included with the runtime and the upstream
license information at:

https://docs.python.org/3/license.html

## Python packages

The packaging workflow installs the WebUI dependencies listed in
`requirements-webui.txt` into `app/.deps`. The build script writes a frozen
dependency list to `python-requirements.lock.txt` in the package root.

Review each dependency's license before redistributing modified packages or
using the bundle in a commercial environment.

## Frontend npm packages

The WebUI JavaScript bundle is built from `package.json` / `package-lock.json`.
It currently includes Konva for the layered input-image editor. Konva is
distributed under the MIT license; review the lock file and upstream package
metadata before redistributing modified bundles.

## iLab CONJURE

iLab CONJURE is licensed under GNU AGPLv3. See `LICENSE` in the package.
