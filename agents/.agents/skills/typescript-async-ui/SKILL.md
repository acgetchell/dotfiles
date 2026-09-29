---
name: typescript-async-ui
description: "Implement or fix TypeScript React interfaces backed by asynchronous APIs, especially TanStack Query/Router, account-scoped data, cancellation, and partial or stale results. Follow the project's existing UI framework."
---

# TypeScript Async UI

Start with the API's state contract and the visible user decisions. Preserve the
project's router, query client, fetch helper, component patterns, and styling.

## Represent observable states

Keep pending, successful empty, partial, stale, failed, and authentication-required
states distinct when the API distinguishes them. Do not replace failures with an
empty array, a false success banner, or a permanent pending promise.

Parse external data before treating it as trusted TypeScript. A generic fetch
helper's type parameter is not runtime validation. Prefer the project's schema
library or a small parser; avoid duplicating validation in every component.

## Query ownership and account changes

- Include all result-affecting inputs and the authorized account identity in query
  keys. Clear or segregate sensitive caches on logout and account changes.
- Do not display one account's cached records while another account is loading.
- Share query options with router loaders where the project uses route preloading.
- Propagate AbortSignal into fetch, including route changes and stale searches.
  Reject or ignore obsolete completions even if cancellation is advisory.
- Keep transport authentication failures distinct from application-level connection
  failures; reconnecting a downstream account need not log out the browser.
- Match retry policy to idempotency and error category. Do not retry denied access
  indefinitely or stack UI retries over a slow server retry budget.

## Rendering and effects

Keep effects tied to real dependencies, not arbitrary sleeps. Derive render state
where possible; avoid storing copies of query data without a user-editing reason.
Preserve useful previous data only when its account/query scope remains correct and
its stale status is visible.

Render untrusted content as text by default. If HTML is required, use an established
sanitization boundary and disable active/remote content according to the product.
Expose evidence links with explicit allowed schemes; never treat received text as
instructions to execute.

## Evidence

With Vitest and Testing Library, assert accessible states and user actions rather
than component internals. Use MSW for HTTP contracts when already installed.
Exercise failed requests, aborts, response reordering, partial results, and account
switches when affected. A visual-only edit does not require a new test framework.
Run the repository's typecheck/build, lint, and relevant test commands.
