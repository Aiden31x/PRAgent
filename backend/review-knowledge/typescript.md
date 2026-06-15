# TypeScript / JavaScript Review Checklist

Apply these checks in addition to the core rubric. This lightweight guide covers
TypeScript and JavaScript pitfalls that appear in non-React code — server-side logic,
CLI tools, Node.js services, shared utilities, and config files.
(If the PR also touches `.tsx`/`.jsx` files, the full React/Next.js/TypeScript guide
applies instead of this one.)

---

## `any` in Public Function Signatures

**Flag `any` in the parameters or return type of exported or public functions.**
`any` removes type checking for the value and everything derived from it. It is a hole
that lets runtime errors bypass TypeScript entirely.

```typescript
// BAD
export function process(data: any): any { ... }

// GOOD
export function process(data: Record<string, unknown>): ProcessedResult { ... }

// GOOD — when type is genuinely unknown (e.g. external I/O), use unknown + guard
function handle(input: unknown): string {
  if (typeof input !== 'string') throw new TypeError('Expected string');
  return input.trim();
}
```

Also flag `as any` — it is `any` dressed up as an assertion and equally dangerous.

---

## Unsafe Type Assertions (`as SomeType`)

**Flag `as T` assertions where `T` has not been verified by a type guard, schema
validation, or equivalent check.**
Type assertions are a promise to TypeScript that has no runtime enforcement. A wrong
assertion silently causes a runtime error on the next property access.

```typescript
// BAD — if the API changes, this crashes at runtime with no compile error
const config = JSON.parse(raw) as AppConfig;

// GOOD — validate at the boundary
import { z } from 'zod';
const config = AppConfigSchema.parse(JSON.parse(raw));   // throws if invalid

// ACCEPTABLE — within a type guard after evidence
if (typeof obj === 'object' && obj !== null && 'id' in obj) {
  const entity = obj as { id: string };
}
```

---

## Floating Promises (Unhandled Rejections)

**Flag calls to `async` functions or other Promise-returning functions whose result is
not awaited, `.catch()`-ed, or explicitly voided.**
In Node.js, unhandled rejections crash the process (Node 15+) or produce cryptic
`UnhandledPromiseRejectionWarning`. In the browser they appear only in console.

```typescript
// BAD
sendEmail(user);          // if this rejects, the error disappears
db.transaction(fn);       // same problem

// GOOD
await sendEmail(user);
sendEmail(user).catch(logger.error);
void sendEmail(user);     // explicit discard — only when intentional
```

Common false-safe pattern to flag: `Promise.all([a(), b()])` where `a()` or `b()` is
an async function but the `Promise.all` itself is not awaited.

---

## `forEach` with an `async` Callback

**Flag `array.forEach(async (item) => { ... })`.**
`forEach` discards the Promises returned by the async callback. Rejections are swallowed
and the surrounding function does not wait for any iteration to finish.

```typescript
// BAD — errors from processItem are swallowed; execution continues immediately
items.forEach(async (item) => {
  await processItem(item);
});

// GOOD — sequential processing
for (const item of items) {
  await processItem(item);
}

// GOOD — parallel (all items at once)
await Promise.all(items.map(processItem));

// GOOD — parallel with concurrency limit
import pLimit from 'p-limit';
const limit = pLimit(5);
await Promise.all(items.map(item => limit(() => processItem(item))));
```

---

## Array Index Access Without an Undefined Guard

**Flag direct array index access (`arr[0]`, `arr[i]`) where the array may be empty or
the index is dynamic, and the value is immediately used without a null/undefined check.**
TypeScript with `noUncheckedIndexedAccess` catches this at compile time, but without
that flag it is a silent runtime risk.

```typescript
// BAD — crashes if arr is empty
const first = arr[0].name;

// GOOD
const first = arr[0]?.name;         // optional chaining
const first = arr[0];
if (first !== undefined) { ... }    // explicit guard

// ALSO GOOD — destructuring with a default
const [first = defaultValue] = arr;
```

Flag this especially in loops where the index comes from external input or a computed
offset.

---

## Optional Chaining Without Null Handling

**Flag long optional chains (`a?.b?.c?.d`) where the final value is used directly
in an expression that would fail if it is `undefined`.**
Optional chaining returns `undefined` when any step is nullish — if that `undefined`
is then passed to a function expecting a real value, it fails.

```typescript
// BAD — if user?.address is undefined, toUpperCase() throws
const city = user?.address?.city.toUpperCase();

// GOOD — guard before use
const city = user?.address?.city?.toUpperCase() ?? 'Unknown';

// GOOD — early return pattern
const city = user?.address?.city;
if (!city) return;
process(city.toUpperCase());
```

---

## `enum` vs Union Type

**Flag `const enum` used in code that crosses module or process boundaries (e.g. APIs,
serialised JSON, shared libraries).**
`const enum` values are inlined at compile time. When two compilation units have different
versions of the enum definition they silently diverge.

```typescript
// RISKY — const enum across module boundaries
export const enum Status { Active = 'active', Inactive = 'inactive' }

// SAFER — string union (serialises naturally, refactor-friendly)
export type Status = 'active' | 'inactive';
export const STATUS = { Active: 'active', Inactive: 'inactive' } as const;
```

This is advisory (flag for discussion), not a hard block.

---

## `Promise.all` vs `Promise.allSettled`

**Flag `Promise.all` when the intent is to process all results regardless of individual
failures.**
`Promise.all` rejects immediately when any Promise rejects, abandoning the rest.
Use `Promise.allSettled` when you want all results (successes and failures) and handle
them individually.

```typescript
// BAD — one failed fetch discards all successful ones
const users = await Promise.all(ids.map(fetchUser));

// GOOD — collect all results, then separate success from failure
const results = await Promise.allSettled(ids.map(fetchUser));
const users   = results.filter(r => r.status === 'fulfilled').map(r => r.value);
const errors  = results.filter(r => r.status === 'rejected').map(r => r.reason);
```

---

## Missing `return` in an `async` Function That Should Return a Value

**Flag `async` functions with a declared non-`void` return type where a code path
implicitly returns `undefined`.**
TypeScript's `noImplicitReturns` catches this, but only if enabled. In loosely-typed
codebases, this results in the caller receiving `undefined` instead of the expected value.

```typescript
// BAD — returns undefined on the else branch
async function getUser(id: string): Promise<User> {
  if (id) {
    return await fetchUser(id);
  }
  // implicit return undefined — TypeScript only catches this with noImplicitReturns
}

// GOOD
async function getUser(id: string): Promise<User> {
  if (!id) throw new Error('id is required');
  return await fetchUser(id);
}
```

---

## Review Checklist Summary

- [ ] No `any` in exported function parameters or return types; no `as any`
- [ ] Type assertions (`as T`) backed by runtime validation or type guards
- [ ] All Promises awaited, caught, or explicitly discarded with `void`
- [ ] No `array.forEach(async ...)` — use `for...of` or `Promise.all`
- [ ] Array index access guarded against `undefined` before use
- [ ] Optional chains produce `undefined` safely — result checked before use
- [ ] `Promise.all` vs `Promise.allSettled` chosen deliberately based on failure semantics
- [ ] No implicit `undefined` returns from non-void async functions
