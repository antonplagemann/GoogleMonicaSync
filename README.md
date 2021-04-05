# Google <-> Monica contact syncing script

This script aims to sync contacts from Google to Monica and eventually back.

## Personal Notes (Braindump)

- SQLite DB columns: MId, GId, FullName, MLastChanged, GLastChanged, GNextSyncToken
- Use Googles Sync Token
- Implement delta and full (initial) sync capabilities
- Implement "source of truth" constant and conflict management
- Define elements (fields) for sync and exclude others
- Implement pip package?
- Use attackIQ code as reference (argument parser, api, etc.)
- Aim for an always consistent state, even in failures
- Only sync new Monica contacts back? (no changed ones)
