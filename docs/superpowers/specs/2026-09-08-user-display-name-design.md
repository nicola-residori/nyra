# User display names in trusted identity

**Date:** 2026-09-08
**Milestone:** M3 — Identity and Voice

## Goal

Nyra keeps Home Assistant's immutable user ID as the identity key while using
the current Home Assistant user name in human-facing responses and Nyra Admin.
For example, a recognized user asking "Chi sono?" receives "Sei Nicola", while
logs and diagnostic details still expose the stable ID needed for correlation.

## Ownership

Router owns the canonical mapping from trusted external identity to display
name. A user reference is keyed by `(provider, user_id)` and contains:

- `provider`, initially `home_assistant`;
- `user_id`, the stable external identifier;
- `display_name`, the current non-empty Home Assistant name;
- `updated_at`, set by Router when trusted metadata is accepted.

Home Assistant is authoritative for its user's display name. Speaker-ID keeps
using only `user_id` for profiles, embeddings, candidates, and biometric
results. Nyra Admin reads enriched data only through Router and never queries
Home Assistant or Speaker-ID directly.

## Trusted synchronization

The Home Assistant integration resolves the authenticated user through
Home Assistant's auth subsystem. It never accepts a display name supplied by
an ESPHome device or an arbitrary service payload.

Home Assistant sends an optional trusted user reference when:

- an authenticated Assist request enters Router;
- enrollment is started or its authenticated panel state is loaded;
- Wake Word capture is started or its authenticated panel state is loaded.

Router validates and upserts the reference. A later trusted interaction with a
new Home Assistant name replaces the previous display name without changing
the user ID or biometric profile. Empty names do not erase a known name.

Opening Nyra Config is sufficient to synchronize the current authenticated
user, which also backfills existing profiles created before this feature.

## Protocol and persistence

Trusted identity and resolved identity contracts gain an optional
`display_name`. Existing callers that send only `user_id` remain compatible.
Router persists user references in its own SQLite state and exposes a small
internal upsert operation used by the Home Assistant adapter.

Biometric audio messages and Speaker-ID storage do not gain mutable user
names. When Speaker-ID returns `identified_user_id`, Router resolves the
current display name from its registry and attaches it to trusted request
context. Identity continuity carries the same resolved user reference for the
session and refreshes its label from the registry when available.

If no mapping exists, Router keeps the correct ID and leaves `display_name`
empty. User-facing code uses a neutral fallback instead of speaking the raw ID;
diagnostic interfaces may show the ID as the fallback label.

## User-facing behavior

Nyra Admin presents the display name as the primary label and the stable ID as
secondary diagnostic information in:

- voice profiles and enrollment samples;
- identity diagnostics, identified user, and candidate rankings;
- Wake Word samples and recorded-by metadata.

Router-provided request context makes both values available to later response
generation. Human-facing responses use `display_name`; identifiers remain for
authorization, storage, correlation, and logs. The feature does not implement
a hardcoded answer for "Chi sono?". It supplies the trusted semantic data that
the response layer needs to answer naturally in the request language.

## Router Admin API enrichment

Existing profile, diagnostic, and Wake Word DTOs gain optional display-name
fields next to their ID fields. Router enriches Speaker-ID responses after
receiving them. Existing clients remain valid because the added fields are
optional.

No endpoint permits Nyra Admin to rename users. Names are changed in Home
Assistant and synchronized through a later authenticated interaction.

## Privacy and failure behavior

Display names are personal metadata. General logs may include stable IDs under
the existing observability policy but do not add display names by default.
Admin may show names to its already authorized operator.

Failure to synchronize a name never blocks enrollment, Wake Word capture, or
normal Assist. Router retains the last trusted non-empty value. If its user
registry is unavailable, the request continues with the stable ID and records
a typed operational failure without trusting unverified metadata.

## Migration

The Router database creates the user-reference table idempotently. Existing
profiles and diagnostics require no Speaker-ID migration. Their IDs are
enriched dynamically after the corresponding Home Assistant user is
synchronized. Nicola's existing profile is backfilled by opening Nyra Config
while authenticated after deployment.

## Verification

Automated tests cover:

- trusted Home Assistant lookup and rejection of forged names;
- create, update, empty-name, restart, and backward-compatible persistence;
- biometric identification and session continuity enrichment;
- Admin profile, diagnostic candidate, and Wake Word rendering;
- absence of display names from general log payloads;
- Italian and English identity context without hardcoded user names;
- existing records before and after user-reference synchronization.

The physical smoke test opens Nyra Config as Nicola, verifies that Admin shows
"Nicola" with the ID as secondary text, then asks "Chi sono?" through Nyra
Mansarda after a successful identification and verifies a natural name-based
response.
