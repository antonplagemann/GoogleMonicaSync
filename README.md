# Google to Monica contact syncing script

## Introduction

This script does a contact syncing from a Google account to a [Monica](https://github.com/monicahq/monica) account. This script is intended for personal use only. It can contain a lot of bugs, errors, and unhandled exceptions, so do a backup before using it. It was programmed very carefully not to screw things up and delete everything but it`s your own risk trusting my words.

That being said: Be welcome to use it, fork and develop it, copy it for your projects, and file issues for bug fixes or improvements you wish for.

## Features

- One-way sync (Google -> Monica)
  - Syncs the following details: first name, last name, middle name, birthday, job title, company
- Advanced matching of already present Monica contacts (e.g. from earlier contact import)
- Fast delta sync using Google sync tokens
- Optional one-time sync-back (Monica -> Google) of new Monica contacts that do not have a corresponding Google contact yet
  - Syncs the following details: first name, last name, middle name, birthday, company, job title, labels, address
- Extensive logging of every change, warning, or error including the affected contact ids and names (File: `Sync.log`)

## Limits

- Do not update [*synced*](#features) details at Monica. As this is a one-way sync, it will overwrite all Monica changes!
- Do not delete contacts at Monica. This will cause a sync error which cou can resolve by doing initial sync again.
- Delta sync will fail if there are more than 7 days between the last sync (Google restriction). In this case, the script will automatically do full sync instead
- Only up to 1000 Google contacts are currently supported (working on it)
- No support for custom Monica gender types. Will be overwritten with standard type O (other)

## Get started

1. Get the [official Python Quickstart script from Google](https://developers.google.com/people/quickstart/python) working.
2. Copy `credentials.json` and `token.pickle` inside the main repository directory.
3. [Download](https://github.com/antonplagemann/GoogleMonicaSync/blob/5caaf3ccb658934fa2f298be6508f8c9848db85c/conf.py) the `conf.py` file, fill in your desired settings and copy it inside the main directory (hint: a Monica token can be retrieved in your account settings, no Oauth client needed).
4. Do a `pip install -r requirements.txt` inside the main repository directory.
5. Run `python GMSync.py -i`

## All sync commands

Initial sync and database reset (interactive):

```bash
python GMSync.py -i
```

Delta or full sync (unattended):

```bash
python GMSync.py
```

## How it works

At first, the script builds an SQLite syncing database named `syncState.db`. To do that it fetches
all Google contacts and all Monica contacts (can take some time) and tries to match them by name.
If there is ambiguity you will be asked whether to link an existing contact or create a new one at Monica. The following details will be stored there:

- Google contact id (unique)
- Monica contact id (unique)
- Google display name
- Monica complete name
- Google last updated timestamp
- Monica last changed timestamp

After building the database, full sync starts. This sync merges every Google and Monica contact according to the sync database. Name and birthday will be overwritten by the Google data, the deceased date will be preserved. This full sync also requests a sync token from Google that is used for every following delta sync. Delta sync is only different from full sync in two points:

- The list of returned contacts from Googly (using the sync token) contains only changed contacts, so the sync will be faster
- It can detect deleted contacts from Google and delete them on Monica

All progress will be printed at running time and will be logged in the `Sync.log` file. If there are any errors at running time the sync will be aborted. Note that there is then a chance for an inconsistent database and you should better rebuild it using `python GMSync.py -i`.

## The conf.py file

In case the link no longer works, this is the sample `conf.py` file.

```python
# Your Monica api token
TOKEN = 'YOUR_TOKEN_HERE'
# Your Monica base url
BASE_URL = 'https://app.monicahq.com/api'
# Create reminders for birthdays and deceased days?
CREATE_REMINDERS = True
# Sync back a new Monica contact to Google once at initialization?
SYNC_BACK = True
# Delete Monica contact if the corresponding Google contact has been deleted?
DELETE_ON_SYNC = True
```

## Feature roadmap (working on it)

- Database consistency check function
- Maybe an additional (pretty printed) sync summary
- Add more sync fields: ~~company, jobtitle,~~ labels, address, phone numbers, emails, notes, contact picture
- Add more one-time sync-back fields: phone numbers, emails, contact picture
- Implement a sync-back cmd-line switch for regularily sync-backs (not only on initial sync)
- Add sync include/exclude labels on both sides
- Think about two-way sync
- Think about a pip package
