# Google to Monica contact syncing script

## Introduction

This script does a contact syncing from a Google account to a [Monica](https://github.com/monicahq/monica) account. This script is intended for my personal use only. It can contain a lot of bugs, errors and unhandled exceptions, so do a backup before using it. It was programmed very carefully not to screw things up and delete everything but it`s your own risk trusting my words.
That beeing said: Be welcome to try it, fork and develop it, use it for your own projects and open issues for bugfixes and improvements you wish for.

## Features (more on the way)

- One-way sync of names and birthdays
- Fast delta sync

## Limits

- The delta sync will fail if there is more than 7 days between the last sync (Gogle restriction)
- Only up to 1000 Google contacts are currently supported (working on it)

## How to setup

- Get the [official Python Quickstart script from Google](https://developers.google.com/people/quickstart/python) working.
- Copy `credentials.json` and `token.pickle` inside the main repository directory.
- Edit the `conf.py` file with your desired settings.
- Do a `pip install -r requirements.txt` inside the main repository directory.
- Run `python GMSync.py --initial`

## How it works

At first the script builds a SQLite syncing database named `syncState.db`. To do that it fetches
all Google contacts and all Monica contacts (can take some time) and tries to match them by name.
If there is ambiguity you will be asked wheter to link an existing contact or create a new one at Monica. The following details will be stored there:

- Google contact id (unique)
- Monica contact id (unique)
- Google display name
- Monica complete name
- Google last updated timestamp
- Monica last changed timestamp

After building the database a full sync starts. This sync merges every Google and Monica contact according to the sync database. Name and birthday will be overwritten by the Google data, deceased date will be preserved. This full sync also requests a sync token from Google that is used for every following delta sync. A delta sync is only different from a full sync in two points:

- The list of returned contacts from Googly (using the sync token) contains only changed contacts, so the sync will be faster.
- It can handle deleted contacts from Google and delete them on Monica too.

All progress will be printed at running time and will be logged in the `Sync.log` file. If there are any errors at running time the sync will be aborted. Note that there is than a chance for an inconsistent database and you should better rebuild it using `python GMSync.py --initial`.

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
- Birthday will always beo overwritten by Google
- Label sync
- Initial Notes sync (if not present at Monica)
- Work details Sync
- Contact picture sync
- Limit 1000 Google contacts
- 7 days sync limit
