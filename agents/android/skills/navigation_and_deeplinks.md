# Navigation and Deep Links

Drive every screen transition through a single NavController and a type-safe Navigation Compose graph, and expose external entry points only through verified Android App Links, never spoofable custom schemes. Routes are `@Serializable` Kotlin types so the compiler, not string keys, guarantees argument correctness; back-stack manipulation is explicit and intentional; and any `https` link that opens the app must be backed by a `.well-known/assetlinks.json` domain-verification record.

## Stack and versions (2026)

- `androidx.navigation:navigation-compose` 2.9.x (stable) is the production default. Type-safe routes built on Kotlin Serialization have been first-class since 2.8.0; do not use the legacy string-route/`NavType` argument APIs in new code.
- Requires the Kotlin Serialization compiler plugin and `org.jetbrains.kotlinx:kotlinx-serialization-core` 1.8.x, with Kotlin 2.1+ and a current Compose BOM (`2026.xx.xx`).
- Hilt navigation integration via `androidx.hilt:hilt-navigation-compose` 1.2.x for `hiltViewModel()` and graph-scoped ViewModels.
- Navigation 3 (`androidx.navigation3`) is in alpha as of 2026: you own the back stack as a `SnapshotStateList` rendered by `NavDisplay`. It is promising for adaptive and multi-pane layouts, but keep stable Navigation Compose for shipping work and adopt Nav3 only on greenfield modules where its back-stack-as-state model earns its keep.

Version catalog excerpt and the serialization plugin:

```kotlin
// build.gradle.kts (module)
plugins {
    alias(libs.plugins.kotlin.serialization) // org.jetbrains.kotlin.plugin.serialization
}
dependencies {
    implementation(libs.androidx.navigation.compose) // 2.9.x
    implementation(libs.kotlinx.serialization.core)   // 1.8.x
    implementation(libs.androidx.hilt.navigation.compose)
}
```

## Type-safe routes with Kotlin Serialization

Each destination is a `@Serializable` type. Use a `data object` for argument-free routes and a `data class` for routes that carry arguments. Defaults make a parameter optional.

```kotlin
@Serializable data object HomeRoute
@Serializable data class ProfileRoute(val userId: String, val tab: Int = 0)
@Serializable data object SettingsGraph        // a nested-graph marker, see below
@Serializable data object SettingsHomeRoute
```

Build the host once and reference routes as instances. `toRoute<T>()` decodes typed arguments on the destination side; there are no `getString("userId")` lookups to typo.

```kotlin
val nav = rememberNavController()
NavHost(navController = nav, startDestination = HomeRoute) {
    composable<HomeRoute> {
        HomeScreen(onOpenProfile = { id -> nav.navigate(ProfileRoute(userId = id)) })
    }
    composable<ProfileRoute> { backStackEntry ->
        val args = backStackEntry.toRoute<ProfileRoute>()   // ProfileRoute(userId, tab)
        ProfileScreen(userId = args.userId, tab = args.tab)
    }
}
```

A ViewModel reads the same arguments straight from `SavedStateHandle`, so you never thread IDs through constructors manually:

```kotlin
@HiltViewModel
class ProfileViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val route: ProfileRoute = savedStateHandle.toRoute()
    // route.userId is available with no key string and no nullability dance.
}
```

Only pass identifiers and small primitives. For a non-primitive argument, register a custom `NavType` via a `typeMap`; do not serialize large payloads into the route, because arguments transit a `Bundle` and the binder transaction caps near 1 MB.

```kotlin
val filterTypeMap = mapOf(typeOf<SearchFilter>() to SearchFilterNavType)
composable<SearchRoute>(typeMap = filterTypeMap) { entry ->
    val args = entry.toRoute<SearchRoute>()  // SearchRoute(filter: SearchFilter)
}
```

## Nested graphs, back stack, and scoping

Group related destinations under a nested graph keyed by a `@Serializable` marker. This gives you a unit to scope shared state to and a clean target for `popUpTo`.

```kotlin
NavHost(navController = nav, startDestination = HomeRoute) {
    composable<HomeRoute> { /* ... */ }
    navigation<SettingsGraph>(startDestination = SettingsHomeRoute) {
        composable<SettingsHomeRoute> { /* ... */ }
        composable<SettingsAboutRoute> { /* ... */ }
    }
}
```

Control the back stack explicitly on every navigation that is not a plain push. `launchSingleTop` prevents duplicate tops; `popUpTo` trims; `saveState`/`restoreState` preserve per-tab back stacks for bottom navigation.

```kotlin
// Bottom-bar tab switch: one entry per tab, state preserved across switches.
nav.navigate(route) {
    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}

// Post-login: clear the auth flow so Back does not return to it.
nav.navigate(HomeRoute) { popUpTo<LoginRoute> { inclusive = true } }
```

Scope a ViewModel to a nested graph so it survives navigation within the graph and is cleared when the graph leaves the back stack. Resolve the parent entry by route type:

```kotlin
val parentEntry = remember(backStackEntry) { nav.getBackStackEntry<SettingsGraph>() }
val settingsVm: SettingsViewModel = hiltViewModel(parentEntry)
```

Return a result to the previous screen through its `SavedStateHandle`, not a global singleton:

```kotlin
// Picker screen, before popping:
nav.previousBackStackEntry?.savedStateHandle?.set("pickedId", id)
nav.popBackStack()

// Caller screen observes:
val handle = nav.currentBackStackEntry?.savedStateHandle
val picked by handle?.getStateFlow<String?>("pickedId", null)!!.collectAsStateWithLifecycle()
```

## Single-activity pattern

Host the entire app in one `Activity` that owns the `NavHost`. Screens are composables, not `Activity` or `Fragment` instances, so transitions are cheap, shared state lives in graph-scoped ViewModels, and there is exactly one place that receives external intents. Keep the `NavController` in composition and pass navigation as lambdas down to screens; never hoist it into a ViewModel, which would leak the `Activity` and break configuration changes. Additional activities are justified only for genuinely separate tasks (a share target, a standalone camera capture), not for in-app screens.

## Deep links and Android App Links

Attach deep links to the destination they resolve to. The type-safe `navDeepLink<T>` derives the URI pattern from the route's fields; the explicit `uriPattern` form gives full control over path versus query placement and is the clearer choice when the URL shape is fixed by a backend contract.

```kotlin
composable<ProfileRoute>(
    deepLinks = listOf(
        // Explicit pattern: {userId} is a path segment, tab is an optional query param.
        navDeepLink { uriPattern = "https://app.example.com/profile/{userId}?tab={tab}" },
    ),
) { entry ->
    val args = entry.toRoute<ProfileRoute>()
}
```

Compose graphs do not auto-generate manifest filters (the `<nav-graph>` tag only works for XML graphs), so author the intent filter by hand on the single host activity. `android:autoVerify="true"` promotes the filter from a generic deep link to a verified Android App Link, and `android:exported="true"` is mandatory on any activity with an intent filter since API 31.

```xml
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="app.example.com" />
    </intent-filter>
</activity>
```

Prefer `https` App Links over a custom scheme (`myapp://`). Custom schemes are not verifiable: any other installed app can register the same scheme and intercept the link, which is an account-takeover and phishing vector. Reserve custom schemes for internal, non-sensitive routing only.

## Domain verification with assetlinks.json

For `autoVerify` to succeed, host a Digital Asset Links statement at `https://app.example.com/.well-known/assetlinks.json` for every host in your filters. The file must be served over HTTPS with `Content-Type: application/json`, return `200` with no redirects, and be reachable without authentication.

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.example.app",
      "sha256_cert_fingerprints": [
        "14:6D:E9:83:C5:73:1C:0A:...:9F"
      ]
    }
  }
]
```

When using Play App Signing, the fingerprint that matters in production is the Play-managed app-signing key, so include the SHA-256 from the Play Console (App integrity), and add your upload-key fingerprint as well so locally built and Play builds both verify. Generate a fingerprint with `keytool -list -v -keystore <keystore>` or copy it from the Play Console.

Verification is per-host: a separate `<data android:host>` entry and a matching statement are required for each subdomain.

## Verifying and testing App Links

```bash
# Launch the URL the way the system would route an intent.
adb shell am start -W -a android.intent.action.VIEW \
  -d "https://app.example.com/profile/42?tab=1" com.example.app

# Inspect per-domain verification state (look for "verified").
adb shell pm get-app-links com.example.app

# Force re-verification after publishing assetlinks.json (API 31+).
adb shell pm verify-app-links --re-verify com.example.app

# Approve a domain locally for testing without a live statement file (API 31+).
adb shell pm set-app-links-user-selection --user cur --package com.example.app true app.example.com
```

Confirm the statement file independently with Google's Digital Asset Links API before relying on it:
`https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://app.example.com&relation=delegate_permission/common.handle_all_urls`. The Play Console App Links assistant reports the same status post-release.

## Common pitfalls

- Custom scheme (`myapp://`) used for a sensitive entry point: unverifiable and hijackable by any app that registers the same scheme. Use an `https` App Link with `autoVerify`.
- `autoVerify="true"` set but `assetlinks.json` missing, behind a redirect, served with the wrong `Content-Type`, or returning non-200: verification reports `failed`/`none` and links silently open in the browser instead of the app.
- Play App Signing in use but only the upload-key fingerprint published: production installs from Play fail verification. Include the Play-managed app-signing SHA-256.
- `android:exported` omitted on the activity that declares intent filters: install/build fails on API 31+ or the filter is ignored.
- Non-primitive object passed in a route without a registered `NavType`: serialization failure at navigate time. Pass an ID and load from a repository.
- Large data stuffed into route arguments: arguments cross a `Bundle`/binder transaction and trip `TransactionTooLargeException` near 1 MB.
- `NavController` hoisted into a ViewModel or retained statically: leaks the `Activity` and breaks across configuration changes. Keep it in composition; pass lambdas down.
- Bottom navigation without `launchSingleTop`/`saveState`/`restoreState`: destinations pile onto the back stack and tab state is lost on switch.
- `previousBackStackEntry` result writes done before checking it exists, or results shuttled through a singleton: prefer the previous entry's `SavedStateHandle`.
- Multiple subdomains covered by one `assetlinks.json`/`<data>` entry: each host needs its own statement and filter.

## Definition of done

- [ ] All destinations are `@Serializable` route types; navigation uses route instances and `toRoute<T>()`, with no string routes or legacy `NavType` argument keys.
- [ ] The app is single-activity: one `NavHost`, screens as composables, `NavController` held in composition and passed down as lambdas.
- [ ] Related screens are grouped under nested graphs; shared state uses graph-scoped ViewModels resolved via `getBackStackEntry<Graph>()`.
- [ ] Back-stack operations are explicit: `launchSingleTop`, `popUpTo`/`inclusive`, and `saveState`/`restoreState` applied where tab or post-auth semantics require them.
- [ ] Route arguments carry only IDs and small primitives; non-primitive args use a registered custom `NavType`.
- [ ] External entry points are `https` Android App Links with `autoVerify="true"` and `android:exported="true"`; custom schemes are limited to internal, non-sensitive routing.
- [ ] A valid `assetlinks.json` is served at `/.well-known/` for every host, over HTTPS, `application/json`, 200, no redirect, with the Play app-signing (and upload) SHA-256 fingerprints.
- [ ] Verification confirmed via `adb shell pm get-app-links` and the Digital Asset Links API; each subdomain has its own filter and statement.
- [ ] Deep-link routing and argument decoding are covered by tests, including a wrong/unverified-host case that does not open the app.
