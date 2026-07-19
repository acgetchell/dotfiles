# Exception Safety Review Checklist

Use this checklist after understanding the operation's actual contract. A checked box is not evidence by itself.

## Contract

- Is the intended exception guarantee maintained on every exit?
- Is the failure channel consistent with callers and neighboring APIs?
- Is the promised guarantee explicitly no-throw, strong, basic, or intentionally weaker?
- Is the public API contract still accurate about failures and post-failure state?
- Can a caller mistake failure for success or lose actionable context?

## Failure paths

- Can failure occur after acquisition or the first mutation?
- Does rollback cover every changed value and external side effect it claims to restore?
- Are all acquired resources cleaned up on every failure path?
- Is the object valid, reusable, or at least safely destructible as promised afterward?
- Can cleanup mask the original failure or throw during unwinding?

## `noexcept`

- Does every reachable callee satisfy the declared exception specification?
- Should the specification be conditional on member or template operations?
- Does move/swap behavior match container and algorithm expectations?
- Can a hidden throwing path reach `noexcept` and call `std::terminate`?
- Would adding or removing `noexcept` change termination, overload, ABI/API, or performance behavior?

## Boundaries

- Are exceptions contained at C ABI, plugin, thread, task, coroutine, callback, and other non-throwing boundaries?
- Do `std::expected`, status/result values, optional results, and error codes preserve category, cause, and context?
- Is each error translated correctly for the receiving abstraction without double-reporting it?
- Do filesystem, networking, parsing, and serialization failures follow the public contract?
- Is deliberate termination visible and justified by the public contract?

## Verification

- Is there a focused test for failure before and after mutation?
- Can allocation, callback, filesystem, networking, parsing, serialization, plugin, or dependency failures be injected or simulated?
- Do tests verify both the reported error and the complete post-failure state?
- Should ownership, invariant, concurrency, or test-quality review also run?
