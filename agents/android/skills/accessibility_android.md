---
name: accessibility-android
description: Governs accessibility semantics, touch-target sizing, Dynamic Type font scaling, color contrast, and reading order for Jetpack Compose screens against WCAG 2.2 AA and Android platform guidance. Use when building, reviewing, or testing Compose UI for TalkBack, Switch Access, font-scale, or contrast compliance.
---

# Accessibility on Android

Make every Compose screen usable by TalkBack, Switch Access, and font/zoom users by treating semantics, touch targets, contrast, and reading order as part of the component contract, not a post-launch cleanup. The target is WCAG 2.2 AA plus Android platform guidance, verified by automated checks in CI and by manual TalkBack passes, because the Accessibility Test Framework catches structural defects but only a human catches a confusing announcement order.

This skill assumes Jetpack Compose with the 2026.x Compose BOM (`androidx.compose.ui:ui`, Material3 `androidx.compose.material3`), `androidx.test.espresso:espresso-accessibility:3.6.x` for instrumentation checks, and `minSdk` high enough that TalkBack and non-linear font scaling (API 34+) are in scope.

## TalkBack and Compose semantics

Compose builds a semantics tree in parallel with the UI tree; TalkBack, Switch Access, and tests read that tree, not your composables. Material3 components carry correct semantics by default. You add or correct semantics when you build custom widgets or override defaults.

- `contentDescription`: the spoken label for non-text content. Set it on `Icon`/`Image` that convey meaning; set it to `null` for purely decorative graphics so TalkBack skips them. Never put the element's type in the text ("button", "image") — `Role` already announces that.
- `Role`: classifies the node so TalkBack announces it correctly and offers the right gestures. Use `Role.Button`, `Role.Checkbox`, `Role.Switch`, `Role.RadioButton`, `Role.Tab`, `Role.Image`, `Role.DropdownList`. Set it via the interaction modifier, not a free-standing string.
- `stateDescription`: the spoken state of a stateful control ("On"/"Off", "3 of 5 stars"). Drives what TalkBack says when the value changes; pair it with `toggleable`/`selectable`.
- `mergeDescendants = true`: collapses a subtree into one focusable node so TalkBack reads "Jane Doe, Online" as a single stop instead of three swipes. Use it on list rows, cards, and list items.
- `clearAndSetSemantics`: deletes the subtree's semantics and replaces them with exactly what you specify. Use it to hide redundant children or to give a complex custom control one clean label. It removes child actions too, so never use it on something interactive unless you re-declare the action.

```kotlin
// Decorative vs meaningful images.
Image(painter = brandPattern, contentDescription = null)               // skipped by TalkBack
Icon(Icons.Filled.Warning, contentDescription = "Validation error")    // announced

// A custom toggle row: one focus stop, correct role and state.
Row(
    modifier = Modifier
        .toggleable(
            value = checked,
            role = Role.Switch,
            onValueChange = onToggle,
        )
        .semantics(mergeDescendants = true) {
            stateDescription = if (checked) "On" else "Off"
        }
        .minimumInteractiveComponentSize(),
) {
    Text("Background sync")
    Spacer(Modifier.weight(1f))
    Switch(checked = checked, onCheckedChange = null)  // null: row owns the action
}

// Override a noisy chart's children with one label.
ComplexChart(
    modifier = Modifier.clearAndSetSemantics {
        contentDescription = "Revenue chart, up 12 percent this quarter"
    },
)
```

Additional semantics that reviewers should expect where relevant: `heading()` on section titles so TalkBack heading navigation works; `liveRegion = LiveRegionMode.Polite` on snackbars, inline validation, and async status so changes are announced without stealing focus; `error("Email is required")` on invalid form fields; and `onClick`/`customActions` to expose swipe or long-press actions that TalkBack cannot perform by gesture. Add `onClickLabel` to `clickable` so TalkBack says "double tap to open details" instead of a generic "activate".

## Touch targets: 48dp minimum

Android guidance and WCAG 2.2 SC 2.5.5 (Target Size, AAA) put the floor at 48dp x 48dp; WCAG 2.2 SC 2.5.8 (AA) allows 24x24 CSS px, but ship to 48dp because that is what motor-impaired and large-finger users actually need. Material3 components enforce this automatically through `minimumInteractiveComponentSize()`, which expands the touch area to 48dp without changing the visual size, so a 24dp icon stays 24dp but is hittable across 48dp.

```kotlin
// A small icon button that is still a 48dp target.
IconButton(onClick = onClose) {                 // IconButton applies the 48dp floor itself
    Icon(Icons.Filled.Close, contentDescription = "Close")
}

// A custom clickable that is visually small must opt in explicitly.
Box(
    Modifier
        .size(24.dp)
        .clickable(onClickLabel = "Dismiss", onClick = onDismiss)
        .minimumInteractiveComponentSize(),       // expands the touchable region to 48dp
)
```

Reject custom interactive elements that set a fixed `size()` under 48dp without `minimumInteractiveComponentSize()`. Do not disable the enforcement via `LocalMinimumInteractiveComponentSize` except in a deliberate, reviewed density-critical layout, and never for primary actions.

## Dynamic Type and font scaling

Specify all text sizes in `sp`, never `dp` or hardcoded pixels, so they respond to the system font-size setting. Android 14 (API 34) introduced non-linear font scaling that lets users reach 200%, capping growth on already-large text while still enlarging body text. Design layouts to reflow, wrap, and scroll at 200%; do not lock text height or truncate at one line for content the user must read.

- Build with `Modifier.verticalScroll` or lazy lists for any screen that can overflow when text grows.
- Avoid `maxLines = 1` with `TextOverflow.Ellipsis` on essential labels; if space is tight, allow wrapping or a larger container.
- Test at the extremes by overriding the configuration in previews and tests:

```kotlin
@Preview(name = "Font 200%", fontScale = 2.0f)
@Preview(name = "Font 85%",  fontScale = 0.85f)
@Composable
private fun ProfileCardPreview() { ProfileCard(sample) }
```

- Read the active scale at runtime with `LocalDensity.current.fontScale` when a layout genuinely must adapt, but prefer letting the layout reflow. Also support display-size/zoom (`densityDpi`) the same way — it scales the whole UI, not just text.

## Color contrast (WCAG 2.2)

Meet WCAG 2.2 contrast minimums in both light and dark themes:

- Normal text (under 18pt, or under 14pt bold): at least 4.5:1 against its background.
- Large text (18pt+, or 14pt+ bold): at least 3:1.
- UI components and meaningful graphics (icons, input borders, focus indicators, chart segments): at least 3:1 (SC 1.4.11).

Verify Material3 `ColorScheme` pairs (for example `onSurfaceVariant` on `surface`, error and outline colors) at their actual values; the default tokens are tuned but custom brand overrides frequently fail. Never encode state with color alone (SC 1.4.1) — a red border needs an icon or text label too. Android 14+ ships system "increase contrast" and "color correction" settings; do not fight them with `android:forceDarkAllowed` hacks. Check ratios with the Material Theme Builder, Android Studio's contrast lint warnings, or a contrast checker against hex values, and validate against the resolved color, not the design-token name.

## Focus and reading order

TalkBack and Switch Access traverse the semantics tree top-to-bottom, left-to-right by default. When visual order and source order diverge (a custom layout, an overlay, an FAB that should read last), correct it with traversal semantics rather than reordering code.

- `Modifier.semantics { isTraversalGroup = true }` groups a subtree so TalkBack finishes it before moving on — use it on a top bar, a bottom bar, and each card.
- `traversalIndex` (a `Float`, lower reads first) reorders within or across groups: give a bottom sheet a lower index than the content behind it so it is announced first.
- Keep `mergeDescendants` rows as single stops so swipe navigation is not flooded with sub-elements.

```kotlin
Modifier
    .semantics { isTraversalGroup = true }   // contained group
// promote an alert ahead of normal content:
Modifier.semantics { traversalIndex = -1f }
```

Do not reach for explicit focus order until default order is wrong; over-specifying `traversalIndex` everywhere is its own bug.

## Accessibility testing

Layer automated checks under manual verification.

- Compose UI tests: assert semantics directly with `composeTestRule.onNodeWithContentDescription("Close").assertIsDisplayed()`, `assertContentDescriptionEquals`, `assertIsToggleable`, and custom `SemanticsMatcher`s. Enable the built-in Accessibility Test Framework checks (touch target size, contrast, duplicate descriptions, clickable-span issues) with `composeTestRule.enableAccessibilityChecks()`; failing checks fail the test.

```kotlin
@get:Rule val composeTestRule = createAndroidComposeRule<MainActivity>()

@Test fun syncRow_isAccessible() {
    composeTestRule.enableAccessibilityChecks()      // ATF: targets, contrast, labels
    composeTestRule.onNodeWithText("Background sync")
        .assertIsDisplayed()
        .assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.ToggleableState))
}
```

- Espresso (View-based or hybrid screens): turn on framework-wide checks once and they run on every `ViewAction`.

```kotlin
@Before fun enableA11yChecks() {
    AccessibilityChecks.enable().setRunChecksFromRootView(true)
}
```

- Accessibility Scanner (Google, from Play Store): run on a real device or emulator for an interactive audit of touch targets, contrast, and missing labels. It uses the same Accessibility Test Framework, so wire it into pre-merge manual QA, not just one-off use.
- Play Console pre-launch reports surface accessibility findings on real devices; review them before promoting a release.
- Manual TalkBack pass is mandatory and non-automatable: enable TalkBack, navigate the screen by swipe only, and confirm every control is reachable, correctly labeled, announces its role and state, reads in a sensible order, and that live regions announce updates without trapping focus.

## Common pitfalls

- `contentDescription` set on decorative images instead of `null`, so TalkBack reads noise; or describing the type ("button icon") that `Role` already speaks.
- Custom clickable elements smaller than 48dp with no `minimumInteractiveComponentSize()` — they pass visual review and fail real thumbs and the ATF target-size check.
- Text sized in `dp` or with hardcoded pixels, so it ignores the user's font-scale setting; or `maxLines = 1` + ellipsis on essential text that then truncates at 200% scale.
- Encoding state with color only (red = error) with no icon or text, failing SC 1.4.1, and brand color overrides that drop `onSurfaceVariant` below 4.5:1.
- `clearAndSetSemantics` placed on an interactive node, silently deleting its click action so TalkBack and Switch Access cannot activate it.
- List rows left unmerged, so every avatar, name, and subtitle is a separate swipe stop and navigation is exhausting.
- Snackbars and inline validation with no `liveRegion`, so TalkBack users never hear the result of their action.
- Reordering composables to fix announcement order instead of using `traversalIndex`/`isTraversalGroup`, which breaks visual layout to patch reading order.
- Relying solely on Accessibility Scanner/ATF and skipping the manual TalkBack pass; automated tools cannot judge whether an announcement is meaningful or correctly ordered.
- `testTagsAsResourceId` not enabled, so UIAutomator/Espresso cannot find Compose nodes by id (set `Modifier.semantics { testTagsAsResourceId = true }` at the root when bridging to View-based tooling).

## Definition of done

- [ ] Every meaningful `Icon`/`Image` has a `contentDescription`; decorative graphics use `null`; no description names the element type.
- [ ] Interactive nodes declare the correct `Role`; stateful controls expose `stateDescription`; custom swipe/long-press actions are exposed via `onClick`/`customActions` with an `onClickLabel`.
- [ ] List rows and cards use `mergeDescendants`; complex custom widgets use `clearAndSetSemantics` only when they re-declare any needed actions.
- [ ] All interactive targets are at least 48dp (`minimumInteractiveComponentSize()` where the visual is smaller); enforcement is not disabled on primary actions.
- [ ] Text is in `sp`; layouts reflow and scroll correctly at `fontScale = 2.0` and at display zoom; previews cover the font-scale extremes.
- [ ] Text and UI contrast meet WCAG 2.2 (4.5:1 body, 3:1 large text and components) in light and dark themes, verified on resolved colors; state is never conveyed by color alone.
- [ ] Reading order is correct under TalkBack, using `isTraversalGroup`/`traversalIndex` where visual and source order diverge; live regions announce async updates.
- [ ] Compose tests call `enableAccessibilityChecks()` and assert key semantics; Espresso enables `AccessibilityChecks` from the root view; both run in CI.
- [ ] Accessibility Scanner and the Play pre-launch report show no outstanding issues, and a manual TalkBack-only navigation pass confirms reachability, labeling, role/state, and order.
