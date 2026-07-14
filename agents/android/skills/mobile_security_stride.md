---
name: mobile-security-stride
description: Governs STRIDE-based mobile threat modeling for Android clients, covering Keystore-backed secrets, certificate pinning, Play Integrity verification, exported-component hardening, and WebView isolation under OWASP MASVS. Use when designing or reviewing security-sensitive Android code such as token storage, network trust, exported components, or WebView usage.
---

# Mobile Security and STRIDE for Android Clients

Treat the Android client as untrusted code running on a possibly hostile device: keep no secret the device does not need, bind every key to hardware, authenticate the channel as well as the user, and let a server-side verdict (not the app) decide whether the runtime is trustworthy. Design against STRIDE per surface, and remember that obfuscation and integrity checks raise an attacker's cost but never replace server-side authorization.

## Standards and threat model baseline

- OWASP MASVS 2.x is the verification standard; MASTG is the test guide. Map app requirements to MASVS-STORAGE, MASVS-CRYPTO, MASVS-NETWORK, MASVS-PLATFORM, MASVS-CODE, and MASVS-RESILIENCE, and pick L1 (all apps) or L2 (high-value: banking, health, money movement) explicitly.
- STRIDE on a mobile client maps to concrete controls:
  - Spoofing: app/device identity via Play Integrity + signed backend auth; user identity via biometrics-gated Keystore keys.
  - Tampering: repackaging and hooking (Frida/Xposed) countered by integrity verdicts and signature checks; data tampering countered by AEAD with associated data.
  - Repudiation: server-side audit logs keyed to authenticated identity, never to client-asserted IDs.
  - Information disclosure: at-rest Keystore crypto, in-transit TLS + pinning, no secrets in the APK, `FLAG_SECURE` and scoped backups.
  - Denial of service: server rate limits; client guards against malformed deep links and oversized intents.
  - Elevation of privilege: explicit `exported`, signature permissions, immutable PendingIntents, WebView isolation, least-privilege runtime permissions.
- The trust boundary is the network edge. Anything the device can compute, an attacker who owns a rooted device can compute too. Authorization decisions live on the server.

## Secrets do not live in the APK

The APK is shipped to the attacker. `strings.xml`, `BuildConfig` fields, Gradle `buildConfigField`, `local.properties`, native `.so` constants, and committed `google-services.json` are all trivially extracted with `apktool` or `jadx`. Anything in the binary is public.

- No API secrets, signing keys, symmetric keys, or third-party tokens in code, resources, or `BuildConfig`. Move them server-side and reach them through an authenticated backend endpoint.
- Public client identifiers (OAuth client_id, Firebase config) are fine in the APK; treat them as identifiers, not secrets, and enforce the real check (PKCE, App Check / Play Integrity, server validation) on the backend.
- Keep release signing keys out of the repo. Use Play App Signing; store the upload key in a CI secret store, never `keystore.properties` in Git.
- Scan every build with a secret scanner (gitleaks, or MobSF on the assembled APK) in CI and fail the pipeline on a hit.

## Android Keystore and data at rest

Generate keys inside the AndroidKeyStore so private/secret key material never enters app memory and is bound to the device's TEE or StrongBox. Prefer AES-256-GCM for symmetric data and gate sensitive keys on user authentication.

```kotlin
val spec = KeyGenParameterSpec.Builder(
    "record_key",
    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
)
    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)  // GCM uses no padding
    .setKeySize(256)
    .setUnlockedDeviceRequired(true)            // API 28+: usable only while screen is unlocked
    .setUserAuthenticationRequired(true)        // require biometric/credential to use the key
    .setUserAuthenticationParameters(           // API 30+: 30s validity, strong biometric or PIN
        30, KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL,
    )
    .build()

val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
try {
    kg.init(spec.toBuilder().setIsStrongBoxBacked(true).build())  // hardware HSM when present
} catch (e: StrongBoxUnavailableException) {
    kg.init(spec)                               // fall back to TEE-backed key
}
val key = kg.generateKey()
// AES-GCM: never reuse an IV with the same key. Let the cipher generate it and store it alongside.
```

For higher-level keyset management, use Google Tink directly. `androidx.security:security-crypto` (EncryptedSharedPreferences / EncryptedFile) is deprecated and frozen at `1.1.0-alpha06`; do not start new code on it. Migrate existing usage to Tink, with the keyset's master key in the Keystore:

```kotlin
// com.google.crypto.tink:tink-android (1.13+)
AeadConfig.register()
val handle = AndroidKeysetManager.Builder()
    .withSharedPref(context, "app_keyset", "app_keyset_pref")
    .withKeyTemplate(KeyTemplates.get("AES256_GCM"))
    .withMasterKeyUri("android-keystore://app_master_key")  // wraps the keyset with a Keystore key
    .build()
    .keysetHandle
val aead = handle.getPrimitive(Aead::class.java)
val ct = aead.encrypt(plaintext, contextInfo)   // contextInfo = associated data, binds ciphertext to context
```

For Room, encrypt the database with SQLCipher (`net.zetetic:sqlcipher-android` 4.6+) using a passphrase wrapped by a Keystore key; do not hardcode the passphrase. Mark sensitive screens `WindowManager.LayoutParams.FLAG_SECURE` to block screenshots and the recents thumbnail.

## Network: TLS, cleartext, and pinning

Disable cleartext globally and pin the certificate chain for backend domains. Pinning defeats a user-installed or malware-installed root CA performing a TLS MITM.

`res/xml/network_security_config.xml`, referenced by `android:networkSecurityConfig` with `android:usesCleartextTraffic="false"`:

```xml
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors><certificates src="system" /></trust-anchors>
    </base-config>
    <domain-config>
        <domain includeSubdomains="true">api.example.com</domain>
        <pin-set expiration="2026-12-31">
            <pin digest="SHA-256">k3XnEYQCK79AtL9GYnT/Q2nX9p2v...</pin>  <!-- leaf or intermediate SPKI -->
            <pin digest="SHA-256">b4ck8pP1nb4ck8pP1nb4ck8pP1n...</pin>  <!-- backup key held offline -->
        </pin-set>
    </domain-config>
</network-security-config>
```

- Pin to the SPKI (subject public key info) hash, not the whole certificate, so rotation within the same key does not break the app. Always ship at least one backup pin to a key you control offline, or a rotation will brick installed clients.
- Set `expiration` so an unmaintained app fails open to system trust rather than hard-breaking; pair this with a forced-update mechanism so you replace pins before they lapse.
- For dynamic pinning prefer OkHttp's `CertificatePinner` (OkHttp 4.12 / 5.x), which lets you ship pins via a hardened config update path:

```kotlin
val pinner = CertificatePinner.Builder()
    .add("api.example.com", "sha256/k3XnEYQCK79AtL9GYnT/Q2nX9p2v...")
    .add("api.example.com", "sha256/b4ck8pP1nb4ck8pP1nb4ck8pP1n...")
    .build()
val client = OkHttpClient.Builder().certificatePinner(pinner).build()
```

- Never ship a debug-only `network_security_config` that trusts user CAs into a release build. Use a separate `debug` source set for the Charles/mitmproxy trust anchor.

## Play Integrity API

SafetyNet Attestation is fully decommissioned. Use the Play Integrity API (`com.google.android.play:integrity` 1.4+) and verify the verdict server-side. The client only relays an opaque token; trusting a client-parsed verdict is the same as trusting the attacker.

```kotlin
val manager = IntegrityManagerFactory.createStandard(context)         // standard, warm-cached provider
val provider = manager.prepareIntegrityToken(
    PrepareIntegrityTokenRequest.builder().setCloudProjectNumber(PROJECT_NUMBER).build(),
).await()

val token = provider.request(
    StandardIntegrityTokenRequest.builder()
        // bind the token to this action and a server-issued nonce to stop replay
        .setRequestHash(sha256Hex(actionId + serverNonce))
        .build(),
).await().token()
// POST token to the backend; decrypt and verify there.
```

- The backend decrypts the token via the Play Integrity API and checks `deviceIntegrity` (`MEETS_DEVICE_INTEGRITY`, `MEETS_STRONG_INTEGRITY` for hardware-backed, `MEETS_BASIC_INTEGRITY`), `appIntegrity.appRecognitionVerdict == PLAY_RECOGNIZED`, and `accountDetails.appLicensingVerdict == LICENSED`. Reject or downgrade based on policy, not on the client's word.
- Always set a `requestHash` from a fresh server nonce so a captured token cannot be replayed for a different action or later session.
- Use Standard requests (low latency, cached) for routine calls and Classic requests sparingly for rare high-value events; Classic is rate-limited and slower. Integrity is a signal that gates server actions, not a client-side gate.

## Runtime permissions and least privilege

Request the minimum and prefer APIs that need no permission at all. Every dangerous permission is attack surface and a Play review risk.

```kotlin
val launcher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
    if (granted) startCapture() else showRationaleAndDegrade()
}
// request in response to a user action, after shouldShowRequestPermissionRationale if appropriate
launcher.launch(Manifest.permission.CAMERA)
```

- Photo/video selection: use the Photo Picker (`ActivityResultContracts.PickVisualMedia`); it requires no storage permission and returns only what the user picked. Drop `READ_EXTERNAL_STORAGE`.
- Media on API 33+ (Android 13): granular `READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO` / `READ_MEDIA_AUDIO`. On API 34+ honor `READ_MEDIA_VISUAL_USER_SELECTED` (partial access) instead of demanding full access.
- `POST_NOTIFICATIONS` is runtime-requested from API 33. Location: request `ACCESS_COARSE_LOCATION` first; only escalate to `FINE`/`BACKGROUND` with a justified, reviewed need.
- Declare a `<queries>` element for the specific packages/intents you resolve; broad package visibility is treated as sensitive.
- Audit the merged manifest (`:app:processReleaseManifest` output) for permissions pulled in transitively by SDKs and strip what you do not use with `tools:node="remove"`.

## Exported components, intents, and PendingIntents

Since API 31 (Android 12) every `activity`, `service`, and `receiver` with an intent filter must set `android:exported` explicitly; default to `false`.

- Anything exported is a public, callable entry point. Validate and sanitize all incoming intent extras and deep-link data; never trust them for authorization. Treat an exported component as a network endpoint reachable by any app.
- Guard cross-app components with a custom permission at `android:protectionLevel="signature"` so only apps signed by your key can invoke them.
- PendingIntents must be `FLAG_IMMUTABLE` on API 31+ unless mutability is genuinely required; a mutable PendingIntent handed to another app lets it fill in the blanks and act as you.

```kotlin
val pi = PendingIntent.getActivity(
    context, 0, intent,
    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
)
```

- Make `Intent`s sent to known recipients explicit (set the package/component); an implicit intent carrying sensitive extras can be intercepted by any app that declares a matching filter.
- Verify App Links with `android:autoVerify="true"` and a published `/.well-known/assetlinks.json` so your HTTPS links open without the disambiguation dialog and cannot be hijacked by a competing filter.
- Set `android:allowBackup="false"`, or define `android:dataExtractionRules` (API 31+) / `fullBackupContent` to exclude tokens and keys from cloud/adb backups. Ship release builds with `android:debuggable="false"` (the default; never override it).

## WebView hardening

A WebView that renders untrusted content inside your app's process and origin is a direct path to your data. Isolate it.

```kotlin
webView.settings.apply {
    javaScriptEnabled = false                  // enable only if the page genuinely needs it
    allowFileAccess = false
    allowContentAccess = false
    allowFileAccessFromFileURLs = false         // deprecated/false: block file:// reading other files
    allowUniversalAccessFromFileURLs = false
    mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
}
```

- Never `addJavascriptInterface` to a WebView that can load untrusted or remote content; a bridged object exposes app capabilities to page JS. If a bridge is unavoidable, restrict the WebView to first-party content and annotate exposed methods `@JavascriptInterface` (already required since API 17).
- Serve bundled HTML/JS through `WebViewAssetLoader` over `https://appassets.androidplatform.net/` instead of `file://`, so the content runs under a real HTTPS origin and `file://` access stays disabled.
- Keep Safe Browsing on (default) and do not call `setSafeBrowsingEnabled(false)`. Keep the WebView/Chrome system component current; ship `androidx.webkit` for back-ported security features and feature detection.
- For displaying third-party web pages, use Custom Tabs (the user's browser, separate process) rather than an in-app WebView so your origin and cookies are never exposed.

## R8 shrinking and obfuscation

Enable R8 for release to shrink, optimize, and obfuscate. This is a cost-raiser against reverse engineering, not a security control: a determined attacker still recovers logic. Pair it with server-side authorization and integrity checks for anything high-value.

```kotlin
android {
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}
```

- R8 full mode is the default since AGP 8. Add `-keep` rules only for reflection/serialization entry points; over-broad keep rules silently disable obfuscation and shrinking.
- Upload the generated `mapping.txt` to the Play Console (or your crash backend) so production stack traces deobfuscate; never commit it or ship it inside the APK.
- Do not store secrets in native code expecting the NDK to hide them; `.so` constants are extracted with `strings`/Ghidra. For genuine anti-tampering, add native integrity self-checks plus Play Integrity, and accept they only delay a skilled reverser.

## Common pitfalls

- API key or signing secret in `strings.xml`, `BuildConfig`, or a committed `google-services.json`; reject the change and rotate the leaked credential.
- EncryptedSharedPreferences in new code: the library is deprecated and frozen; require Tink or a Keystore-wrapped scheme instead.
- AES-GCM with a reused or hardcoded IV, which destroys confidentiality and integrity for that key. The IV must be unique per encryption.
- Certificate pinning with no backup pin and no `expiration`, guaranteeing a future hard-brick on rotation.
- A debug `network_security_config` that trusts user CAs leaking into the release build, defeating pinning.
- Parsing the Play Integrity verdict on-device and trusting it, instead of verifying the token server-side with a bound nonce.
- `android:exported="true"` without an intent filter justification or a signature permission; an exported component is callable by any installed app.
- Mutable PendingIntent (missing `FLAG_IMMUTABLE`) on API 31+, handing another app a fillable intent that runs with your identity.
- `addJavascriptInterface` on a WebView that loads remote/untrusted URLs; this bridges app capability to page JavaScript.
- Treating R8 obfuscation as a security boundary, or shipping `mapping.txt` in the APK.
- `android:allowBackup="true"` (default) with tokens/keys included, exfiltrating secrets via `adb backup` or cloud backup.
- Requesting broad permissions (`READ_EXTERNAL_STORAGE`, `ACCESS_FINE_LOCATION`) when the Photo Picker or coarse location would do.

## Definition of done

- [ ] No secrets in code, resources, `BuildConfig`, or committed config; CI secret scanning (gitleaks/MobSF) gates the build; release signing uses Play App Signing with the upload key in a CI secret store.
- [ ] Sensitive data at rest uses AndroidKeyStore-generated AES-256-GCM (StrongBox when available, user-auth-gated for high-value keys) or Tink with a Keystore-wrapped keyset; no new EncryptedSharedPreferences; SQLCipher passphrase is Keystore-wrapped.
- [ ] `cleartextTrafficPermitted="false"` globally; backend domains pinned to SPKI hashes with a backup pin and an `expiration`, paired with a forced-update path; no user-CA trust in release.
- [ ] Play Integrity tokens are bound to a server nonce/requestHash and verified server-side; device/app/licensing verdicts drive a server-side decision, never a client-only gate.
- [ ] Permissions are minimal; Photo Picker and granular/partial media access replace broad storage; runtime requests follow user action; the merged manifest is audited for SDK-added permissions.
- [ ] Every component sets `android:exported` explicitly and defaults to false; cross-app entry points use signature permissions; intent extras and deep links are validated; App Links are `autoVerify` with a published assetlinks.json.
- [ ] PendingIntents are `FLAG_IMMUTABLE` unless mutability is required and justified; intents to known recipients are explicit.
- [ ] WebViews disable JavaScript and file access unless required, never bridge to untrusted content, serve local assets via `WebViewAssetLoader` over HTTPS, keep Safe Browsing on, and use Custom Tabs for third-party pages.
- [ ] Release builds enable R8 (`minifyEnabled`, `shrinkResources`) with tight keep rules; `mapping.txt` is uploaded to the Play Console and excluded from the APK; obfuscation is not relied on as the only control.
- [ ] `allowBackup="false"` or scoped `dataExtractionRules`; `debuggable="false"`; sensitive screens set `FLAG_SECURE`.
- [ ] A STRIDE pass per surface (auth, storage, network, IPC/components, WebView) is recorded with the mitigating control for each threat, and MASVS L1/L2 level is documented; instrumentation tests cover wrong-pin rejection, missing-permission paths, and exported-component input validation.
