# Migrating to Gopnik 4

Cerberus was renamed to Gopnik. Version 4 changes the repository, plugin,
skill, helper, configuration, and environment identifiers. It is an identity
cutover, not an in-place plugin update.

## Safe order

1. Follow the current [install guide](install.md) and verify that `gopnik`,
   `gopnik-critic`, and `gopnik-setup` are discoverable.
2. Find the old plugin selector, repository-local skill directories, and
   configuration without deleting them.
3. Migrate exactly one valid configuration to its matching new path.
4. Verify Gopnik again.
5. Remove only the exact old targets you found.

Do not merge two configuration files automatically. If old and new files both
exist, compare them and ask the operator which one is authoritative.

## Identifier map

| Before 4.0 | Gopnik 4 |
| --- | --- |
| `cerberus@concordloom` | `gopnik@madduck-tech` |
| `cerberus`, `cerberus-critic`, `cerberus-setup` | `gopnik`, `gopnik-critic`, `gopnik-setup` |
| `cerberus_setup.py` | `gopnik_setup.py` |
| `cerberus.json` | `gopnik.json` |
| `.claude/cerberus.json` | `.claude/gopnik.json` |
| `.codex/cerberus.json` | `.codex/gopnik.json` |
| `CERBERUS_*` | `GOPNIK_*` |

Preserve the configuration contents byte-for-byte when only its path changes.
If the file is tracked, confirm the repository rename before changing it.

## Remove the old installation

Only after Gopnik works, uninstall the old native plugin with the host's exact
selector or remove the exact old repository-local skill directories. Do not
delete a whole `.claude/skills` or `.agents/skills` directory, and remove only
the link when a target is a symlink.

Configuration remains project knowledge. Delete it only with separate operator
confirmation after its Gopnik counterpart has been verified.
