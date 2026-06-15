# React / Next.js / TypeScript Review Checklist

Apply these checks in addition to the core rubric. This guide covers TypeScript type-safety
pitfalls and React-specific patterns including hooks, component design, Next.js Server
Components, and React 19 features.

---

## TypeScript: `any` Type

**Flag every use of `any` in public function signatures, exported types, and API boundaries.**
`any` disables type checking entirely for that value and all values derived from it. Every
`any` in a public signature is a hole through which runtime errors silently enter.

```typescript
// BAD
function processData(data: any) {
  return data.value;   // no type checking — crashes if data lacks .value
}

// GOOD — use a proper interface or unknown + type guard
interface DataPayload { value: string }
function processData(data: DataPayload): string {
  return data.value;
}

// GOOD — for genuinely unknown external data, use unknown + guard
function processUnknown(data: unknown): string {
  if (typeof data === 'object' && data !== null && 'value' in data) {
    return (data as { value: string }).value;
  }
  throw new Error('Invalid data shape');
}
```

---

## TypeScript: Unsafe Type Assertions

**Flag `as SomeType` assertions that bypass type checking without any narrowing.**
Type assertions tell TypeScript "trust me" — if the assertion is wrong, the error surfaces
at runtime, not at compile time.

```typescript
// BAD — if the API returns a different shape, this is a silent runtime bug
const user = response.data as User;

// GOOD — validate the shape at the boundary (e.g. with Zod)
const user = UserSchema.parse(response.data);

// ACCEPTABLE — assertion within a type guard after evidence
if (typeof data === 'object' && 'id' in data) {
  const user = data as User;
}
```

Flag `as any` especially — it completely removes type safety from the value.

---

## TypeScript: Floating Promises

**Flag `async` function calls whose return value (the Promise) is not awaited, `.catch()`-ed,
or explicitly discarded with `void`.**
An unhandled Promise rejection becomes a silent failure in Node.js or a browser console
warning with no stack trace in the right place.

```typescript
// BAD — if save() rejects, the error is swallowed
save();

// GOOD choices
await save();
save().catch(logger.error);
void save();   // explicit discard — only when deliberate
```

---

## TypeScript: `forEach` with an `async` Callback

**Flag `array.forEach(async (item) => { ... })`.**
`forEach` ignores the returned Promises — rejections are swallowed and the outer function
does not wait for any of the async work to complete before continuing.

```typescript
// BAD — errors swallowed, execution continues before items are processed
items.forEach(async (item) => {
  await processItem(item);
});

// GOOD — sequential
for (const item of items) {
  await processItem(item);
}

// GOOD — parallel
await Promise.all(items.map(processItem));
```

---

## TypeScript: Discriminated Union Exhaustiveness

**Flag `switch` or `if/else` chains over a discriminated union that lack an exhaustive check.**
When a new variant is added to the union, an inexhaustive check silently falls through.

```typescript
type Status = 'active' | 'inactive' | 'pending';

// BAD — adding 'suspended' to Status causes silent fallthrough
function label(s: Status): string {
  switch (s) {
    case 'active':   return 'Active';
    case 'inactive': return 'Inactive';
    // 'pending' missing — returns undefined
  }
}

// GOOD — exhaustive check with never
function label(s: Status): string {
  switch (s) {
    case 'active':   return 'Active';
    case 'inactive': return 'Inactive';
    case 'pending':  return 'Pending';
    default:
      const _exhaustive: never = s;
      throw new Error(`Unhandled status: ${_exhaustive}`);
  }
}
```

---

## React: Hooks Called Conditionally

**Flag any hook call (`useState`, `useEffect`, `useRef`, `useContext`, custom hooks, etc.)
inside a conditional, loop, or nested function.**
React relies on hook call order being stable across renders. Conditional hooks break this
and cause confusing state corruption.

```tsx
// BAD
function Component({ isLoggedIn }) {
  if (isLoggedIn) {
    const [user, setUser] = useState(null);  // violates Rules of Hooks
  }
}

// GOOD — call all hooks unconditionally at the top
function Component({ isLoggedIn }) {
  const [user, setUser] = useState(null);
  if (!isLoggedIn) return <LoginPrompt />;
  return <Profile user={user} />;
}
```

---

## React: `useEffect` Missing Dependencies

**Flag `useEffect` callbacks that reference props or state variables not listed in the
dependency array.**
This causes stale closures: the effect runs once with the initial values and never updates
when the referenced values change.

```tsx
// BAD — userId changes are ignored; always fetches the first userId
useEffect(() => {
  fetchUser(userId).then(setUser);
}, []);   // userId missing

// GOOD
useEffect(() => {
  fetchUser(userId).then(setUser);
}, [userId]);
```

---

## React: Stale Closure in `useEffect`

**Flag effects that read state or props from an outer scope without listing them as
dependencies — especially when the effect sets up a timer, subscription, or event listener.**

```tsx
// BAD — the interval always logs the initial value of count
useEffect(() => {
  const id = setInterval(() => {
    console.log(count);   // stale — always 0
  }, 1000);
  return () => clearInterval(id);
}, []);   // count missing from deps

// GOOD — either add count to deps or use a ref
const countRef = useRef(count);
useEffect(() => { countRef.current = count; }, [count]);

useEffect(() => {
  const id = setInterval(() => {
    console.log(countRef.current);   // always fresh
  }, 1000);
  return () => clearInterval(id);
}, []);
```

---

## React: `useEffect` with Async Function and No Cleanup

**Flag `useEffect(() => { asyncFn(); }, [...])` where the async operation updates state
but has no cancellation/cleanup.**
If the component unmounts (or the effect re-runs) before the async operation completes,
calling `setState` on an unmounted component causes a warning and may apply stale data.

```tsx
// BAD — sets state after unmount if userId changes quickly
useEffect(() => {
  fetchUser(userId).then(setUser);
}, [userId]);

// GOOD — use a cancellation flag or AbortController
useEffect(() => {
  let cancelled = false;
  fetchUser(userId).then(data => {
    if (!cancelled) setUser(data);
  });
  return () => { cancelled = true; };
}, [userId]);

// ALSO GOOD — AbortController for fetch
useEffect(() => {
  const controller = new AbortController();
  fetch(`/api/users/${userId}`, { signal: controller.signal })
    .then(r => r.json())
    .then(setUser)
    .catch(e => { if (e.name !== 'AbortError') throw e; });
  return () => controller.abort();
}, [userId]);
```

---

## React: `useEffect` for Derived State (Anti-Pattern)

**Flag `useEffect` that exists solely to compute derived state and call `setState`.**
This causes an unnecessary extra render and is a React anti-pattern. Compute derived values
inline during render or with `useMemo`.

```tsx
// BAD — extra render, complex lifecycle
const [filteredItems, setFilteredItems] = useState([]);
useEffect(() => {
  setFilteredItems(items.filter(i => i.active));
}, [items]);

// GOOD — derive synchronously
const filteredItems = useMemo(() => items.filter(i => i.active), [items]);
```

---

## React: `useMemo` / `useCallback` Without `React.memo`

**Flag `useMemo` or `useCallback` used on values that are only passed to non-memoized children.**
`useMemo`/`useCallback` only prevent re-renders when the child is wrapped in `React.memo`.
Without it, the memoisation only adds overhead.

```tsx
// BAD — MemoizedChild is not a React.memo component; useCallback does nothing
const handleClick = useCallback(() => { ... }, []);
return <RegularChild onClick={handleClick} />;

// GOOD — wrap the child that receives the stable reference
const MemoizedChild = React.memo(function Child({ onClick }) { ... });
const handleClick = useCallback(() => { ... }, []);
return <MemoizedChild onClick={handleClick} />;
```

Conversely, flag `useMemo` computing a simple value (a string, a small array literal)
that doesn't involve expensive computation — that's premature optimisation.

---

## React: Component Defined Inside Another Component's Render

**Flag component definitions (`function Foo() {...}` or `const Foo = () => ...`) nested
inside another component's body.**
A new component type is created on every parent render, causing the child to remount
(not just re-render) every time. All child state is destroyed.

```tsx
// BAD
function Parent() {
  function Child() { return <div>hi</div>; }   // new type each render!
  return <Child />;
}

// GOOD — define at module scope
function Child() { return <div>hi</div>; }
function Parent() { return <Child />; }
```

---

## React: `key` Prop Using Array Index for Reorderable Lists

**Flag `key={index}` on list items when the list can be reordered, filtered, or have
items inserted/removed.**
Using the index as key causes React to reuse DOM nodes for wrong items, corrupting
uncontrolled input state and causing subtle rendering bugs.

```tsx
// BAD — index as key when list is sortable/filterable
{items.map((item, index) => (
  <Row key={index} item={item} />
))}

// GOOD — use a stable, unique ID
{items.map(item => (
  <Row key={item.id} item={item} />
))}
```

Using index is acceptable only for static, append-only lists that never reorder.

---

## React: Direct State Mutation

**Flag any code that mutates state or props directly instead of producing a new value.**
React's reconciler relies on reference equality to detect changes. Direct mutation means
React never sees the change and the UI doesn't update.

```tsx
// BAD
const [items, setItems] = useState([]);
items.push(newItem);      // mutation — React won't re-render
items[0].name = 'Bob';    // nested mutation

// GOOD
setItems([...items, newItem]);
setItems(items.map((item, i) => i === 0 ? { ...item, name: 'Bob' } : item));
```

---

## Next.js: `use client` Placed Too High in the Tree

**Flag `'use client'` on layout or high-level wrapper components when only a leaf needs
interactivity.**
Marking a parent `'use client'` converts the entire subtree to client components, losing
the performance and data-fetching benefits of Server Components for all children.

```tsx
// BAD — entire layout becomes a client bundle
// app/layout.tsx
'use client';
export default function Layout({ children }) { ... }

// GOOD — push 'use client' to the smallest interactive leaf
// app/components/Counter.tsx
'use client';
export function Counter() { ... }

// app/layout.tsx — stays a Server Component
export default function Layout({ children }) {
  return <div><Counter />{children}</div>;
}
```

---

## Next.js: Server Component Using Hooks or Browser APIs

**Flag hooks (`useState`, `useEffect`, etc.) or browser-only globals (`window`, `document`,
`localStorage`) used in Server Components** (files without `'use client'`).
These crash at build time or silently produce wrong output during SSR.

```tsx
// BAD — app/page.tsx is a Server Component by default
function Page() {
  const [count, setCount] = useState(0);  // Error: hook in Server Component
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}

// GOOD — extract interactive parts into a 'use client' component
'use client';
export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}
// app/page.tsx (Server Component)
async function Page() {
  const data = await fetchData();
  return <div><h1>{data.title}</h1><Counter /></div>;
}
```

---

## Next.js / React: Missing Error Boundary Around Suspense

**Flag `<Suspense>` components that are not wrapped in an Error Boundary.**
When a suspended component throws an error during data fetching, without an Error Boundary
the entire application tree crashes.

```tsx
// BAD
<Suspense fallback={<Loading />}>
  <DataComponent />
</Suspense>

// GOOD
<ErrorBoundary fallback={<ErrorMessage />}>
  <Suspense fallback={<Loading />}>
    <DataComponent />
  </Suspense>
</ErrorBoundary>
```

---

## React 19: `useFormStatus` Called Outside a `<form>`

**Flag `useFormStatus()` called in a component that is not a descendant of a `<form>` element.**
`useFormStatus` reads form state from the nearest `<form>` ancestor via React context.
Calling it at the same level as the `<form>` — or outside one entirely — always returns
`{ pending: false }` with no error.

```tsx
// BAD — useFormStatus called in the same component as <form>
function BadForm() {
  const { pending } = useFormStatus();   // always false!
  return (
    <form action={action}>
      <button disabled={pending}>Submit</button>
    </form>
  );
}

// GOOD — call useFormStatus inside a child of <form>
function SubmitButton() {
  const { pending } = useFormStatus();
  return <button disabled={pending}>{pending ? 'Saving…' : 'Submit'}</button>;
}
function GoodForm() {
  return (
    <form action={action}>
      <SubmitButton />
    </form>
  );
}
```

---

## React 19: `useOptimistic` for Irreversible Operations

**Flag `useOptimistic` used for operations that cannot be rolled back** (payments, sending
emails, deleting data with no soft-delete).
`useOptimistic` reverts to the server value on error, but the side effect already occurred.
The user sees the UI revert after believing the action succeeded, which is confusing and
potentially dangerous.

```tsx
// BAD — payment is charged even if the UI rolls back
const [optimisticBalance, addOptimistic] = useOptimistic(balance, ...);
const handlePay = async () => {
  addOptimistic(-amount);
  await chargeCard(amount);   // if this succeeds, money is gone regardless of UI
};

// GOOD — use optimistic UI only for reversible or idempotent operations
// (likes, follows, toggles, drafts)
```

---

## Review Checklist Summary

**TypeScript**
- [ ] No `any` in public function signatures or exported types
- [ ] `as` type assertions backed by evidence or validation (e.g. Zod)
- [ ] All Promise-returning calls are awaited, caught, or explicitly voided
- [ ] No `array.forEach(async ...)` — use `for...of` or `Promise.all`
- [ ] Discriminated union `switch` statements have an exhaustive `never` default

**React Hooks**
- [ ] All hooks called unconditionally at the top level
- [ ] `useEffect` dependency arrays are complete
- [ ] `useEffect` with async work has cancellation / cleanup
- [ ] No `useEffect` computing derived state — use `useMemo` instead
- [ ] `useMemo`/`useCallback` used alongside `React.memo`; not used on trivial values

**Component Design**
- [ ] No component definitions nested inside another component's body
- [ ] List items use stable unique IDs as `key`, not array indices
- [ ] State updates produce new values — no direct mutation of state or props

**Next.js / Server Components**
- [ ] `'use client'` scoped to leaf components that need interactivity
- [ ] No hooks or browser globals in Server Components
- [ ] Every `<Suspense>` wrapped in an Error Boundary

**React 19**
- [ ] `useFormStatus` only called inside a child of `<form>`
- [ ] `useOptimistic` not used for irreversible side effects
