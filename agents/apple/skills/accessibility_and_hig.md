---
name: accessibility-and-hig
description: Governs VoiceOver labeling and traits, Dynamic Type scaling, color contrast, Reduce Motion and Reduce Transparency handling, and Human Interface Guidelines conventions across Apple platforms. Use when building or reviewing SwiftUI or UIKit UI for accessibility, or writing an Accessibility Inspector or performAccessibilityAudit test.
---

# Accessibility and Human Interface Guidelines

Accessibility is a build requirement, not a late pass: every interactive element must carry a correct label, value, and traits, scale with Dynamic Type, meet contrast minimums, and respect the user's motion and transparency settings, with every screen verified in the Accessibility Inspector and a passing XCUITest audit before merge. Treat the accessibility tree as a first-class API surface and Apple's Human Interface Guidelines (HIG) as the contract for layout, hit targets, and platform conventions across iOS 26, iPadOS 26, macOS 26, watchOS 26, and tvOS 26 (Xcode 26, Swift 6.x, SF Symbols 7).

## Standards baseline and platform settings

- Targets: WCAG 2.2 AA for contrast and text resizing; Apple HIG for native conventions. The two overlap but HIG is the binding reference on Apple platforms.
- The system exposes assistive settings through SwiftUI environment values; read them, never hardcode an assumption. Key values: `\.accessibilityReduceMotion`, `\.accessibilityReduceTransparency`, `\.accessibilityDifferentiateWithoutColor`, `\.accessibilityInvertColors`, `\.accessibilityVoiceOverEnabled`, `\.accessibilitySwitchControlEnabled`, `\.legibilityWeight` (bold text), and `\.dynamicTypeSize`.
- UIKit/AppKit equivalents live on `UIAccessibility` (for example `UIAccessibility.isReduceMotionEnabled`, `.isVoiceOverRunning`) with change notifications like `UIAccessibility.reduceMotionStatusDidChangeNotification`.
- Assistive technologies you must not break: VoiceOver, Voice Control, Switch Control, Full Keyboard Access, and Dynamic Type. A view that only works under touch and sighted reading is incomplete.

## VoiceOver and the accessibility tree

Every element VoiceOver focuses needs a label (what it is), optionally a value (its current state), traits (how it behaves), and a hint (what happens on activation). SwiftUI infers labels for `Text`, `Button`, and `Label`, but anything custom needs explicit modifiers.

```swift
// Icon-only control: SF Symbol alone announces nothing useful.
Button {
    viewModel.toggleFavorite()
} label: {
    Image(systemName: isFavorite ? "heart.fill" : "heart")
}
.accessibilityLabel("Favorite")
.accessibilityValue(isFavorite ? "On" : "Off")
.accessibilityHint("Adds this item to your favorites")
// Do NOT put "button" in the label; the .isButton trait already announces it.

// Compose a card into one element instead of four separate stops.
HStack {
    Image("avatar").accessibilityHidden(true)   // decorative -> hide it
    VStack(alignment: .leading) {
        Text(user.name)
        Text(user.role).foregroundStyle(.secondary)
    }
}
.accessibilityElement(children: .combine)        // one focusable element
.accessibilityAddTraits(.isButton)
```

Rules that reviewers should enforce:

- `accessibilityElement(children:)` modes: `.combine` merges descendant labels into one element, `.ignore` drops children and uses only the modifiers you set, `.contain` keeps the subtree as a navigable container (use for sections/lists). Pick deliberately; the default leaves every subview as a separate stop.
- Labels are short noun phrases, sentence case, no trailing period, and never repeat the trait ("Delete", not "Delete button"). Values carry mutable state ("75 percent", "Selected"). Hints are full sentences describing the result and are the only place a verb-led instruction belongs.
- Traits are behavior, not decoration: `.isButton`, `.isHeader` (critical for rotor navigation), `.isLink`, `.isImage`, `.isSelected`, `.isModal` (for sheets/alerts that should trap focus), `.isToggle` (iOS 17+), `.updatesFrequently` (live timers/progress), and `.allowsDirectInteraction` (drawing canvases). Use `.accessibilityRemoveTraits` to strip an inferred trait that is wrong.
- Mark purely decorative imagery `accessibilityHidden(true)` so VoiceOver does not stop on it. Never hide an interactive element.
- For dynamic UI, move VoiceOver focus and announce changes with `AccessibilityNotification.Announcement("Saved").post()` or `\.accessibilityFocus` rather than letting focus jump unpredictably.

## Dynamic Type and layout

Use the eleven semantic text styles (`.largeTitle` through `.caption2`) so text scales from xSmall up to the five accessibility sizes (AX1-AX5). Fixed point sizes do not scale and are a defect.

```swift
Text("Heading").font(.title2)                 // scales automatically
Text("Body copy").font(.body)

// Custom font that still scales: relativeTo maps it onto a text style.
Text("Brand").font(.custom("Inter", size: 17, relativeTo: .body))

// Scale non-text metrics (padding, icon box, corner radius) with text.
@ScaledMetric(relativeTo: .body) private var iconSize: CGFloat = 24
Image(systemName: "bell").frame(width: iconSize, height: iconSize)
```

- Support the full range including accessibility sizes. Only clamp where a layout genuinely cannot adapt, and clamp narrowly: `.dynamicTypeSize(...DynamicTypeSize.accessibility3)`. Never cap at `.large` to dodge layout work.
- At AX sizes, horizontal layouts break. Reflow with `ViewThatFits` (swap an `HStack` for a `VStack` when space runs out) and prefer scroll containers over truncation. Test every screen at AX5.
- Never truncate or clip primary content to fit; the Accessibility Inspector flags `textClipped`.
- UIKit: set `adjustsFontForContentSizeCategory = true` and build fonts through `UIFontMetrics(forTextStyle:).scaledFont(for:)`. A raw `UIFont.systemFont(ofSize:)` will not scale.

## Color and contrast

- Contrast minimums (WCAG 2.2 AA, enforced by the Inspector): 4.5:1 for body text, 3:1 for large text (>= 17pt bold or >= 20pt regular, roughly), and 3:1 for meaningful UI component boundaries and graphics. Aim higher; these are floors.
- Use semantic colors (`Color.primary`, `.secondary`, `Color(.label)`, `Color(.systemBackground)`) and asset-catalog colors with light/dark and high-contrast variants. They adapt to dark mode and the Increase Contrast setting automatically; hardcoded hex values do not.
- Never encode meaning in color alone. Honor `\.accessibilityDifferentiateWithoutColor` by adding a shape, icon, or text label.

```swift
@Environment(\.accessibilityDifferentiateWithoutColor) private var noColor
HStack {
    Circle().fill(status.color).frame(width: 10, height: 10)
    if noColor { Image(systemName: status.symbolName) }  // shape backs up the hue
    Text(status.title)
}
```

## Motion, transparency, and color settings

```swift
@Environment(\.accessibilityReduceMotion) private var reduceMotion
@Environment(\.accessibilityReduceTransparency) private var reduceTransparency

// Replace a large parallax/zoom transition with a cross-fade when asked.
content
    .transition(reduceMotion ? .opacity : .scale.combined(with: .opacity))

withAnimation(reduceMotion ? nil : .spring(duration: 0.4)) {
    isExpanded.toggle()
}

// Respect Reduce Transparency: drop the blur for an opaque fill.
background(
    reduceTransparency
        ? AnyShapeStyle(Color(.systemBackground))
        : AnyShapeStyle(.ultraThinMaterial)
)
```

- Reduce Motion: remove large-scale movement, parallax, and spring/zoom transitions; substitute fades or no animation. SF Symbol effects and essential progress indicators are fine. Disabling Reduce Motion behavior entirely is a defect for users prone to motion sickness.
- Reduce Transparency: swap `Material`/blur backgrounds for opaque fills so text over them stays legible.
- For animated images and flashing content honor `\.accessibilityPlayAnimatedImages` and avoid content that flashes more than three times per second (seizure risk).

## Accessibility focus and custom actions

```swift
enum Field { case email, error }
@AccessibilityFocusState private var focus: Field?

TextField("Email", text: $email)
    .accessibilityFocused($focus, equals: .email)

if let message = errorMessage {
    Text(message)
        .accessibilityFocused($focus, equals: .error)
        .onAppear { focus = .error }   // pull VoiceOver to the new error
}

// Expose swipe/contextual actions to VoiceOver and Full Keyboard Access.
rowView
    .accessibilityAction(named: "Archive") { archive(item) }
    .accessibilityAction(named: "Delete") { delete(item) }
```

- Drive VoiceOver focus to newly surfaced content (validation errors, expanded panels, freshly loaded results) with `@AccessibilityFocusState`; do not leave focus stranded on the old element.
- Any gesture-only interaction (swipe-to-delete, long-press menu, custom drag) must have an equivalent `accessibilityAction`, or it is unreachable for assistive-tech users.
- Provide custom rotor entries with `.accessibilityRotor` for long, structured content (headings, search hits) so VoiceOver users can jump rather than swipe linearly.

## SF Symbols

SF Symbols 7 ships 6,900+ symbols that align to text baselines and scale with Dynamic Type when rendered as font-based images. Prefer `Label` so the symbol pairs with a real text label for free.

```swift
Label("Notifications", systemImage: "bell.badge")     // text gives VoiceOver its label

Image(systemName: "wifi")
    .imageScale(.large)
    .font(.title2)                                     // scales with Dynamic Type
    .symbolRenderingMode(.hierarchical)                // monochrome | hierarchical | palette | multicolor
    .symbolEffect(.pulse, isActive: isSyncing)         // honors Reduce Motion
```

- Use system symbols over custom glyphs; they inherit weight, scale, and locale/RTL mirroring, and many carry built-in accessibility descriptions.
- A bare `Image(systemName:)` used as a control still needs an `accessibilityLabel`; the glyph name is not a label.
- Symbol animations route through `.symbolEffect`, which the system suppresses under Reduce Motion. Do not reimplement them with raw transforms that ignore the setting.

## HIG compliance essentials

- Minimum hit target is 44x44 points (iOS/iPadOS); enforce with `.frame(minWidth: 44, minHeight: 44)` or generous `contentShape`. The Inspector's hit-region audit flags smaller targets. On watchOS follow the platform's larger minimums; on tvOS rely on focus-engine spacing.
- Use standard controls and navigation containers (`NavigationStack`, `TabView`, `.sheet`, `.toolbar`, swipe actions) so platform behaviors, keyboard support, and accessibility come built in. Re-creating a back button or tab bar by hand loses all of that.
- Respect safe areas, the keyboard avoidance behavior, and platform idioms (pull-to-refresh, edit mode, context menus). Support both light and dark appearance and all orientations the device offers.
- Localize every user-facing string and design for text expansion and right-to-left layouts (use leading/trailing, not left/right). Pseudolocalization surfaces clipping early.
- For tiny controls expose the Large Content Viewer with `.accessibilityShowsLargeContentViewer()` so users can long-press to magnify the label.

## Verification: Accessibility Inspector and audits

The Accessibility Inspector ships with Xcode 26 (Xcode > Open Developer Tool > Accessibility Inspector). Use all three modes:

- Inspection: hover any element to read its label, value, traits, and frame; confirm they match intent.
- Audit: run the per-screen automated audit to catch missing labels, low contrast, clipped text, small hit targets, and elements with no description. Drive the simulator through every screen and state.
- Settings: live-toggle Dynamic Type size, Increase Contrast, Reduce Transparency, Reduce Motion, and bold text without leaving the app, then re-check layout.

Codify it as a regression gate in XCUITest (Xcode 15+ API), scoped to the audit types you care about:

```swift
func testHomeScreenAccessibility() throws {
    let app = XCUIApplication()
    app.launch()
    try app.performAccessibilityAudit(for: [
        .contrast, .dynamicType, .elementDetection,
        .hitRegion, .sufficientElementDescription, .textClipped, .trait,
    ])
}
```

Run the app under VoiceOver on a real device for the primary flows; the automated audit cannot judge whether the reading order and announcements make sense. Manually walk: tab to every control, swipe through in order, activate with a double-tap, and confirm focus lands sensibly after navigation and errors.

## Common pitfalls

- Icon-only buttons with no `accessibilityLabel`: VoiceOver reads nothing or the raw symbol name. Reject any `Image(systemName:)` control without a label.
- Label that repeats the trait ("Submit button", "Home tab"): the trait already announces it, so VoiceOver says it twice.
- Decorative images left in the tree instead of `accessibilityHidden(true)`, padding navigation with meaningless stops.
- Fixed point sizes (`.font(.system(size: 15))`) or UIKit fonts without `UIFontMetrics`/`adjustsFontForContentSizeCategory`: text does not scale and fails the Dynamic Type audit.
- Clamping Dynamic Type at `.large` to avoid reflow work; AX users get tiny text. Clamp narrowly and only where unavoidable.
- Meaning carried by color alone with no shape/text fallback, breaking for color-blind users and `differentiateWithoutColor`.
- Animations and material blurs that ignore `accessibilityReduceMotion` / `accessibilityReduceTransparency`.
- Hardcoded hex colors that fail contrast in dark mode or under Increase Contrast; use semantic/asset colors instead.
- Swipe- or gesture-only actions with no `accessibilityAction` equivalent, leaving them unreachable.
- Hit targets under 44x44 points, flagged by the Inspector's hit-region audit.
- Custom-built navigation/controls that drop the system's keyboard and assistive support.
- Shipping with no `performAccessibilityAudit` test and no real-device VoiceOver pass.

## Definition of done

- [ ] Every interactive element has a correct label, value where state applies, accurate traits, and a hint where the action is non-obvious; decorative content is `accessibilityHidden(true)`.
- [ ] Custom groupings use the right `accessibilityElement(children:)` mode; reading and focus order are verified under VoiceOver on a real device for primary flows.
- [ ] All text uses semantic text styles (or `relativeTo:` custom fonts) and scales correctly through AX5; non-text metrics use `@ScaledMetric`; layouts reflow with `ViewThatFits` and never clip primary content.
- [ ] Contrast meets WCAG 2.2 AA (4.5:1 text, 3:1 large text and UI components) in light, dark, and Increase Contrast; colors are semantic/asset-based; meaning never relies on color alone.
- [ ] `accessibilityReduceMotion`, `accessibilityReduceTransparency`, and `accessibilityDifferentiateWithoutColor` are honored; symbol effects use `.symbolEffect`; no content flashes more than three times per second.
- [ ] VoiceOver focus is driven to new errors/content with `@AccessibilityFocusState`; every gesture-only interaction has an `accessibilityAction`.
- [ ] SF Symbols are used over custom glyphs, paired via `Label` where possible, and icon-only controls still carry an explicit label.
- [ ] HIG conventions hold: standard controls/containers, >= 44x44pt hit targets, safe-area and dark-mode support, localization, and RTL correctness.
- [ ] The Accessibility Inspector audit passes on every screen, and a scoped `performAccessibilityAudit` XCUITest runs green in CI.
