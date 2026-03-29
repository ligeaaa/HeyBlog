# shared/ Boundary

`shared/` exists for code that is genuinely cross-service and stable.

Allowed:

- configuration parsing
- small HTTP clients shared by multiple services
- pure data structures or contracts
- tiny utility helpers with no service ownership

Not allowed:

- crawler-specific pipeline logic
- backend-only orchestration
- search-only indexing behavior
- persistence-only repository logic
- “temporary dumping ground” code that has not been assigned an owner

Rule of thumb:

If only one deployable service needs the code, keep it inside that service.
