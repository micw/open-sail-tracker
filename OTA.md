# Firmware over-the-air update design

Status: design proposal. OTA is not implemented. It must not be enabled for production while update authorization and firmware authenticity are unresolved.

## Goals

The tracker should be updatable over the cellular connection without physical access while preserving these properties:

- an interrupted download continues to leave a bootable firmware image;
- only firmware issued by the project can be installed;
- an image for one hardware target cannot be installed on another target;
- a faulty image rolls back automatically;
- updates do not disrupt an active event unexpectedly;
- low battery, weak connectivity, or hostile network input cannot easily cause repeated downloads;
- rollout progress and failures are observable without exposing device credentials.

Both the H802 and a possible T-PCIE/A7672E target need the same release process but separate firmware artifacts.

## Current constraints

The current H802 firmware:

- uses SIM7670G AT commands and the modem's UDP socket instead of an ESP32 IP stack;
- sends plain, unauthenticated CoAP;
- does not parse application responses or receive commands;
- has no provisioned per-device application key;
- is built for 16 MB flash with `ota_0` and `ota_1` partitions of 3 MB each;
- has no image confirmation, rollback policy, or firmware-version telemetry.

The existing partition table is already structurally suitable for dual-image OTA:

```text
nvs       0x005000
otadata   0x002000
ota_0     0x300000
ota_1     0x300000
ffat      0x9e0000
coredump  0x010000
```

An update can therefore be written to the inactive 3 MB application partition while the current image continues running. The application size must remain below the partition limit.

The H802 proof-of-concept build measured on 2026-09-20 uses 303,765 bytes of its 3,145,728-byte application slot. There is ample room for an OTA client at this stage, but CI should continue checking the artifact size for every firmware target.

## Security requirements

OTA would turn the current lack of transport authentication from a telemetry risk into a remote-code-execution and fleet-compromise risk. An unsigned OTA mechanism must not be deployed, even for a supposedly private URL.

The design needs two distinct controls:

1. **Update authorization** prevents arbitrary parties from making a device spend battery and cellular data on downloads.
2. **Image authenticity** prevents an unauthorized firmware image from being installed even if transport or server infrastructure is compromised.

HTTPS alone is useful but is not the complete trust model. The preferred production protection is a signed image or signed manifest verified against a public key embedded in the device. The private release-signing key must not be present in the firmware, repository, container images, or ordinary deployment configuration.

ESP32 Secure Boot V2 and flash encryption provide the strongest platform enforcement, but secure-boot provisioning includes irreversible eFuse operations and needs a deliberate manufacturing process. Before that is introduced, application-level signature verification can support development, but it must be reviewed carefully and must not be presented as equivalent to hardware-enforced secure boot.

A SHA-256 digest detects corruption but is not authentication if the digest comes from the same unauthenticated source as the image. The digest must be covered by a trusted signature or delivered through a mutually authenticated control channel.

## Recommended architecture

### Control plane

Each tracker periodically or explicitly checks for an update instruction. The instruction should be authenticated with the future per-device communication key and contain or reference a signed manifest.

A manifest should include at least:

```text
product: open-sail-tracker
hardware_target: h802 | t-pcie-a7672e
version: immutable semantic version
build_id: immutable source/build identifier
image_size: bytes
image_sha256: digest
image_url: HTTPS URL
minimum_bootloader/security_version: optional policy value
release_channel: test | staged | stable
not_before/not_after: bounded rollout window
signature: release-key signature over all security-relevant fields
```

The device must reject:

- the wrong hardware target;
- an image larger than the inactive OTA partition;
- malformed lengths, hashes, versions, URLs, or signatures;
- older versions unless a separately authenticated recovery policy allows downgrade;
- an already failed version until a new rollout instruction is issued;
- repeated requests for the already running version.

Rollouts should be addressable by device or cohort and support pause and cancellation. Updates should normally be disabled during an active event and allowed only above a conservative battery threshold or while external power is available.

### Data plane

Three implementation approaches are possible.

#### 1. Modem-native HTTPS, streamed to the ESP32 update API

The modem performs HTTPS and exposes response data over AT commands. Firmware reads bounded chunks over UART and writes them sequentially to the inactive OTA partition.

Advantages:

- preserves the existing AT-command network architecture;
- avoids adding PPP and a full ESP32 cellular network stack;
- can be implemented separately for each supported modem;
- RAM use remains bounded with chunked reads.

Risks:

- SIMCom HTTP/TLS commands and certificate handling vary by model and firmware revision;
- binary UART reads need strict length handling and recovery from unsolicited modem output;
- the behavior of SIM7670G and A7672E must be verified on hardware;
- resumable download may be difficult depending on HTTP range support in the modem API.

This is the recommended first implementation for the current architecture, subject to successful modem tests.

#### 2. PPP over serial plus ESP32 HTTPS OTA

The ESP32 establishes PPP and uses its normal TCP/IP, TLS, HTTP, and OTA libraries.

Advantages:

- standard ESP-IDF networking and OTA facilities;
- consistent HTTPS behavior across modem models;
- easier HTTP redirects, ranges, certificates, and diagnostics.

Risks:

- substantial change from the current direct AT-socket design;
- PPP data mode complicates concurrent GNSS and control commands on one modem UART;
- more RAM, state management, reconnect logic, and test effort.

This may become preferable if the general transport layer later moves to PPP, but it is too large a prerequisite for the first OTA proof of concept.

#### 3. Custom CoAP/UDP block transfer

The existing UDP socket could fetch numbered blocks with acknowledgements and retries.

Advantages:

- reuses the current transport;
- small protocol overhead;
- complete control over pacing and resumption.

Risks:

- reinvents reliable transfer, congestion behavior, integrity checking, and authorization;
- considerably enlarges the attack surface of the UDP parser;
- needs careful persistence and retry design;
- offers no benefit over HTTPS sufficient to justify the initial complexity.

This is not recommended for the first implementation. CoAP can carry the authenticated update instruction while HTTPS carries the signed binary.

## Installation and rollback sequence

A safe update should proceed as follows:

1. Receive and authenticate an update instruction.
2. Confirm hardware target, version policy, event state, battery state, partition capacity, and rollout window.
3. Fetch and verify the signed manifest.
4. Download the exact declared number of bytes into the inactive OTA partition using bounded chunks.
5. Calculate SHA-256 while streaming and compare it with the signed manifest.
6. Verify the firmware signature according to the selected signing design.
7. Atomically select the new partition as the next boot target.
8. Persist an `installing` state and reboot.
9. Run a bounded self-test in the new image.
10. Mark the image valid only after essential hardware initialization and backend communication succeed.
11. Allow the bootloader to roll back if the image crashes, fails its self-test, or does not confirm within the defined policy.
12. Report success or rollback through status telemetry.

An interrupted download must not change the boot partition. Power loss after boot selection must still leave either the new image or rollback image bootable.

The self-test must not require a GNSS fix, because indoor startup could then cause a valid firmware to roll back. Appropriate checks include internal configuration validity, modem UART response, acceptable partition metadata, and successful authenticated contact with the backend. Network failure policy needs a bounded grace period so a temporary outage does not cause an endless rollback loop.

## Battery and operational policy

Firmware updates are energy-intensive and should not start merely because a new version exists. The initial policy should require all of the following:

- no active race/event assignment, or an explicit administrative override;
- a stable battery reading above an experimentally selected threshold, initially likely at least 3.8 V;
- no active low-voltage or modem-brownout indication;
- acceptable signal quality and network stability;
- a cooldown after failed attempts;
- enough declared image size allowance within the device's cellular-data budget.

The device should finish safely if voltage falls during download: abort writing, retain the old boot selection, close the download, and return to normal operation or controlled low-battery shutdown. A partially written inactive partition is harmless and can be erased or overwritten during the next authorized attempt.

## Telemetry additions

Status telemetry should eventually expose bounded identifiers and state values, not URLs or secrets:

- running firmware version and build ID;
- hardware target and board revision;
- active OTA partition;
- offered target version;
- OTA state: idle, offered, downloading, verifying, pending reboot, validating, successful, failed, rolled back;
- downloaded bytes or coarse progress;
- last OTA error code;
- reset reason and rollback reason;
- timestamp or uptime of the last attempt.

Protocol changes must preserve wire compatibility deliberately. Adding these fields likely requires a new status-packet version or a separately versioned diagnostics resource rather than silently changing the current fixed 58-byte payload.

## Release and key handling

The build pipeline should produce, per hardware target:

- the flashable firmware binary;
- its exact size and SHA-256 digest;
- an immutable signed manifest;
- release notes and compatibility metadata.

Backend and web images can continue sharing a product release version, but device firmware artifacts must also identify their hardware target. The OTA service must never infer target compatibility from the version string alone.

Production signing should be a separate release step with tightly restricted access. Development and production trust roots must differ so that a development image cannot be installed on production trackers.

## Phased implementation

### Phase 0: groundwork

- add an explicit firmware version, build ID, and hardware target;
- report them in diagnostics without breaking the existing packet format;
- add host-side tests for manifest parsing and all length/range checks;
- confirm rollback support in the selected Arduino/ESP-IDF build configuration;
- enforce the 3 MB slot limit in CI and report firmware-size changes.

### Phase 1: local OTA proof of concept

- update over USB/Wi-Fi or a controlled local byte stream into the inactive partition;
- verify interruption safety, hash checking, boot selection, image confirmation, and rollback;
- do not expose a remote update command.

### Phase 2: cellular test-channel OTA

- validate modem-native HTTPS and chunked binary reads on the SIM7670G;
- require a signed manifest and test-only signing key;
- permit only explicitly enrolled test devices;
- add rate limits and OTA telemetry.

### Phase 3: production security

- deploy authenticated per-device control messages;
- establish protected production signing and staged rollouts;
- decide and document Secure Boot V2 and flash-encryption provisioning;
- test power loss, corrupt images, wrong-target images, expired manifests, replay, downgrade, server failure, and network interruption;
- port and repeat all modem-specific tests for the T-PCIE/A7672E target if adopted.

## Open questions

- Which exact SIM7670G firmware and AT commands provide reliable HTTPS streaming?
- Does the candidate A7672E daughterboard expose equivalent HTTP/TLS behavior?
- Is modem TLS certificate validation practical on both targets, or should TLS terminate through PPP?
- Which signature scheme will be used before and after secure-boot provisioning?
- What event-management state authorizes an update?
- Which battery threshold and signal-quality policy are safe based on measurements?
- What server or object store hosts immutable binaries without exposing reusable device credentials in URLs?
- How is a physically inaccessible device recovered if both application slots become unusable?
