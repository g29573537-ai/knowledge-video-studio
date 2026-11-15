# Research before declaring unavailability

Permanent practice for all future tasks:

1. Before writing "tool X cannot do this", inspect the tool itself:
   - run `tool --help`;
   - run `--help` for every relevant subcommand;
   - read the tool's documentation or source if needed.
2. If the direct command is unavailable, try reasonable alternatives and record
   their actual output.
3. Only after these checks may the agent state that a capability is unavailable.
4. Never rely on an assumption when the tool can be queried directly.
