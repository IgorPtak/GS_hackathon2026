# UI kit cheat sheet

Tokens live in `src/index.css`; use classes like `bg-card`, `text-ink-2`, `border-hairline`, `rounded-card`. Never hard-code a colour. Full rules: `docs/ui-design.md`.

- Sizes: `text-caption|meta|body|row|card-title|page|hero`; weights 400/500/600 only; add `num` for live numbers.
- Radii: `rounded-window` 28, `rounded-card` 20, `rounded-tile` 14, `rounded-input` 12, `rounded-full` pills.
- `Button` (`variant` primary|secondary|ghost|danger, `size` md|lg, `isLoading`, `icon`): one primary per toolbar.
- `Pill` filter toggle (`isActive`, `count`, `onToggle`); `Toolbar` + `ToolbarDivider` hold one primary then pills.
- `Card` (`as`, `isPadded`), `EmptyState` (`icon`, sentence, `action`), `Skeleton`, `Spinner`.
- `Avatar name team size`, `SeverityDot severity`, `StatusChip tone icon`, `CountBadge count` (bumps on increase).
- `Timeline` + `TimelineStep state="pending|running|done|failed|skipped" title meta`; use plain-language titles.
- Forms: `Field label help error` gives `id` and aria props to its render-prop child (`TextInput`, `Select`); `MultiSelect`, `Toggle`, `Segmented`.
- `Dialog isOpen onClose title footer`: native `<dialog>`, Esc and click-outside close it.
- Toasts: `const toast = useToast(); toast.show("Approved")` (`"error"` tone stays longer). Needs `ToastProvider` (the shell has it).
- `<Icon name="inbox" size={20} />` from `icons.tsx` (own SVG set, `currentColor`); add icons there, not from a library.
- `Tooltip label side`, `BeaconLogo`, `PRODUCT_NAME` from `lib/brand.ts`; team colours via `lib/teams.ts`.
- The shell renders `PageHeader` (title, team) and the scrolling `bg-panel` area with 32 px padding; pages start with a `Toolbar` or cards and should not render their own page title.
- Rail Phone item lives at `/simulator`; `/phone` is the full-screen route; `/demo` is reserved. `?team=rates` and `?theme=dark` set team and appearance (handy for demos).
