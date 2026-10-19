# Sponsorship Filter

> Copy this file to `sponsorship-filter.md`. Your `sponsorship-filter.md` is gitignored.

A generic work-authorization filter applied during job search and before ranking. It does **not** assume any specific visa type. Behavior is driven by `requiresSponsorship` in your profile.

## Rules

Read `requiresSponsorship` (true/false) from your profile.

- **If `requiresSponsorship` is false:** keep all roles. This filter does nothing.
- **If `requiresSponsorship` is true:**
  - A posting that **explicitly states no sponsorship**, or requires **citizenship** or an **active security clearance** -> **DROP it.**
  - A posting that is **silent** on sponsorship -> **keep it, but tag it `unconfirmed`** so you can verify before investing time.

When in doubt, tag rather than guess. Do not assume sponsorship is unavailable just because it is not mentioned.

## Common red-flag phrases (DROP when `requiresSponsorship` is true)

- "must be authorized to work without sponsorship"
- "we do not sponsor"
- "no visa sponsorship available now or in the future"
- "US citizenship required"
- "must be a US citizen"
- "active security clearance required"
- "must be able to obtain a security clearance"
- "US Person as defined by ITAR"
- "permanent resident or citizen only"

> Add region- or role-specific phrases you encounter here.

## Tagging

- `ok` — sponsorship explicitly available, or you do not require it.
- `unconfirmed` — posting is silent; verify with the recruiter or job page before applying.
