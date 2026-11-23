# Field Inspection

Offline inspection forms for the cargo-screening team. Diagnostics photographs are processed on the device; no image or recognised text is sent to a server.

Use Node 22 and `npm ci` for a checkout. `npm run android` and `npm run ios` build the native development client; the camera modules need a native build rather than Expo Go. `npm run typecheck` covers the mobile sources and replay script.

Forms use the ordered controls in `src/forms`, with brace-delimited bindings in templates and plain keys in saved inspection data. The diagnostics capture button passes recognised lines to the same autofill function as the fixture replay tool. Capture notes are in `/app/fixtures/README.md`.
