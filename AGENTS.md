# Repository Instructions

## Language

- Write technical documentation in English.
- Write source code, code comments, identifiers, commit messages, CI configuration, packaging metadata, and operational documentation in English.
- Keep the main `README.md` in German for now.
- Keep user-facing interfaces and user-visible application text in German for now.
- Existing German technical documents may be translated when they are substantially revised.

## Project

- The project name is **Open Sail Tracker**.
- The Git repository is `git@github.com:micw/open-sail-tracker.git`.
- Keep firmware, backend, protocol, deployment, web application, and tooling in this monorepository.

## Engineering

- Never commit credentials, SIM identifiers, device keys, private provisioning data, or environment-specific secrets.
- Treat UDP and CoAP input as untrusted and validate lengths, types, ranges, and protocol fields before processing it.
- Keep the first transport proof of concept simple. Plain CoAP is acceptable only for the explicitly documented test stage; production communication must be encrypted and authenticated.
- Add focused automated tests for protocol encoders and decoders.
- Preserve wire compatibility deliberately and document protocol changes.
