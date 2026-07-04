# Navigation

This skill governs routing in Flutter apps: go_router as the standard router, typed routes over string paths, redirect-based guards, deep links, ShellRoute for persistent chrome, state restoration, and explicit result contracts for dialogs and routes. The stance: navigation is declarative app state, defined centrally and driven by the application layer — widgets say what happened, the router decides where the user goes.

## go_router and typed routes

Use `go_router` (13.x or later; the package is maintained by the Flutter team and is the assumed default here) with `go_router_builder` codegen so every route is a typed class instead of a string:

```dart
@TypedGoRoute<TradeRoute>(path: '/portfolio/:accountId/trade')
class TradeRoute extends GoRouteData with _$TradeRoute {
  const TradeRoute({required this.accountId, this.symbol});
  final String accountId;
  final String? symbol;   // query parameter

  @override
  Widget build(BuildContext context, GoRouterState state) =>
      TradePage(accountId: accountId, symbol: symbol);
}

// call site — a rename or new required param is now a compile error:
const TradeRoute(accountId: 'acc-1', symbol: 'AAPL').go(context);
```

Raw `context.go('/portfolio/$id/trade')` strings are a review reject in codegen projects: typos and parameter drift surface at runtime in production instead of at compile time. Define the whole route table in one file under `core/router/`, and know the verbs: `go` replaces the stack per the route hierarchy, `push` stacks on top, `replace` swaps the top. Using `go` where `push` is intended silently destroys back-stack state.

## Redirect guards

Authentication and onboarding gates live in the router's `redirect`, not in page `initState` checks scattered across screens. Make the guard a pure function of app state, and give the router a `refreshListenable` so a mid-session logout re-evaluates redirects immediately:

```dart
GoRouter(
  refreshListenable: authStateListenable,   // e.g. bridged from a Riverpod provider
  redirect: (context, state) {
    final loggedIn = auth.isLoggedIn;
    final goingToLogin = state.matchedLocation == '/login';
    if (!loggedIn && !goingToLogin) {
      return '/login?from=${Uri.encodeComponent(state.uri.toString())}';
    }
    if (loggedIn && goingToLogin) return '/';
    return null;  // no redirect
  },
)
```

Preserve the intended destination in a `from` query parameter and honor it after login — dropping the user on the home screen after a deep-link login is a defect. Redirect loops (A redirects to B, B back to A) throw after go_router's loop limit; keep the guard's decision table small and unit-test it as a pure function.

## Deep links

Every route path is a deep-link surface. Configure Android App Links (`autoVerify` intent filter plus `assetlinks.json`) and iOS Universal Links (Associated Domains plus `apple-app-site-association`); custom URI schemes are fallback only, since they lack ownership verification. Deep-link handling must tolerate cold start: parameters arrive as strings, so validate and coerce them at the route boundary and route garbage to a not-found screen rather than throwing. Never trust deep-link parameters for authorization — a link to `/portfolio/other-users-account` must fail server-side, and the guard applies to deep links exactly as to in-app navigation.

## ShellRoute and nested navigation

Persistent chrome (bottom navigation bar, side rail) uses `StatefulShellRoute.indexedStack`: each tab gets its own `Navigator` branch, so per-tab stacks and scroll positions survive tab switches. Plain `ShellRoute` fits a shared wrapper without independent branch state. Do not simulate tabs by swapping full routes with `go` — that rebuilds the shell and destroys tab state on every switch. Give each branch its own `navigatorKey` when you must push above the shell (full-screen flows over the tab bar).

## State restoration

Set `restorationScopeId` on `MaterialApp.router` and pass `restorationScopeId` to the router so the navigation stack survives OS-initiated process death (backgrounded app evicted for memory). Screens that hold local view state additionally implement `RestorationMixin` with `RestorableProperty` fields. Test restoration on Android with "Don't keep activities" enabled; a trading app that loses its half-completed order form on a phone call is a bug report.

## Dialog and route result contracts

Any route or dialog that returns a value declares that type explicitly at both ends, and callers handle the null (dismissed) case:

```dart
final confirmed = await context.push<bool>('/trade/confirm', extra: order);
// or: showDialog<bool>(...) with Navigator.pop(context, true/false)
if (confirmed ?? false) { await submit(order); }
```

Popping without a value must be a valid outcome — barrier taps and system back return null. Use `context.pop(result)` symmetrically with the declared type; an untyped `pop()` feeding a caller that expects `bool` is a latent cast failure. For flows spanning several screens (multi-step wizard), return one result object from the flow's entry route rather than threading values through each step.

## Common pitfalls

- String-built paths at call sites in a project with typed routes; parameter drift becomes a runtime 404.
- Auth checks in `initState` of individual pages instead of the central `redirect`; deep links and restored sessions bypass them.
- Missing `refreshListenable`, so logout does not eject the user from protected screens until the next navigation.
- `go` used for drill-in navigation where `push` was intended, wiping the back stack the user expects.
- Tabs implemented by swapping top-level routes instead of `StatefulShellRoute`, losing per-tab stacks and scroll positions.
- Deep-link parameters trusted for authorization or parsed without validation, crashing on malformed URLs.
- `showDialog` results consumed without handling the null/dismissed case.
- Navigation triggered from deep inside the widget tree with business logic attached; the decision belongs to application-layer state feeding the router.

## Definition of done

- [ ] All routes are defined centrally and generated via `go_router_builder`; no string path literals at call sites.
- [ ] Guards live in `redirect` as a pure, unit-tested function; `refreshListenable` re-evaluates them on auth-state change; post-login honors the original destination.
- [ ] Android App Links and iOS Universal Links are configured and verified; every deep-link parameter is validated at the route boundary and authorization is enforced server-side.
- [ ] Persistent chrome uses `StatefulShellRoute.indexedStack`; per-tab stacks survive tab switches.
- [ ] `restorationScopeId` is set and restoration verified with "Don't keep activities"; stateful forms use `RestorationMixin`.
- [ ] Every value-returning route/dialog has a typed result contract and callers handle dismissal (null) explicitly.
- [ ] Widget tests cover the guard matrix (logged out, logged in, deep link, restored) using the real router config.
