[comment]: <> "LTeX: language=en-US"

# Google to Monica contact syncing script

## Introduction

This script does a contact syncing from a Google account to a [Monica](https://github.com/monicahq/monica) account. This script is intended for personal use only. It can contain all kinds of bugs, errors, and unhandled exceptions, so please do a backup before using it. It was programmed very carefully not to do bad things and delete everything, but it's your own risk trusting my words.

That being said: Be welcome to use it, fork it, copy it for your own projects, and file issues for bug fixes or improvements.

## Features

- One-way sync (Google → Monica)
  - Syncs the following details: first name, last name, middle name, birthday, job title, company, addresses, phone numbers, email addresses, labels (tags), notes (see [limits](#limits))
- Advanced matching of already present Monica contacts (e.g. from earlier contact import)
- User choice prompt before any modification to your Monica data during initial sync (you can choose to abort before the script makes any change).
- Fast delta sync using Google sync tokens
- Optional sync-back (Monica → Google) of new Monica contacts that do not have a corresponding Google contact yet
  - Syncs the following details: first name, last name, middle name, birthday, job title, company, addresses, phone numbers, email addresses, labels (tags)
- Extensive logging of every change, warning, or error including the affected contact ID and name (File: `Sync.log`)

## Limits

- **Do not update [*synced*](#features) details at Monica.** As this is a one-way sync, it will overwrite all Monica changes to these fields! Of course, you can continue to use activities, notes, journal, relationships and almost any other Monica feature. Just don't update [name, birthday, job info, ...](#features) at Monica.
- **Do not delete contacts at Monica.** This will cause a sync error which you can resolve by doing initial sync again.
- Monica limits API calls to 60 per minute. As every contact needs *at least* 2 API calls, **the script can not sync more than 30 contacts per minute** (thus affecting primarily initial and full sync).
- Delta sync will fail if there are more than 7 days between the last sync (Google restriction). In this case, the script will automatically do full sync instead
- No support for custom Monica gender types. Will be overwritten with standard type O (other) during sync.
- No support for nickname and gender sync (support can be added, file an issue if you want it). Nicknames and genders will be overwritten during sync
- A label itself won't be deleted automatically if it has been removed from the last contact
- If there is a Google note it will be synced with exactly one Monica note. To this end, a small text will be added to the synced note at Monica. This makes it easy for you to distinguish synced and Monica-only notes. This means **you can update and create as many *additional* notes as you want at Monica**, they will not be overwritten.
- Monica contacts require a first name. If a Google contact does not have any name, it will be skipped.

## Known bugs

- Sometimes the Google API returns more contacts than necessary. This is not an issue because the sync will match the last known update timestamps and skip the contact if nothing has changed.
- Birthdays on 29. Feb will be synced as 01. March :-)
- Pay attention when you *merge* Google contacts on the web GUI. In this case the contact will get recreated at Monica during sync if `DELETE_ON_SYNC` is set to `True`(because Google assigns a new contact ID). That means all Monica-specific data will be deleted. You can avoid this by merging them manually (copy over the details by hand) or doing initial sync `-i` again afterwards.

## Get started

0. Install Python 3.9 or newer
1. Get the [official Python Quick-start script from Google](https://developers.google.com/people/quickstart/python) working.
2. Copy `credentials.json` and `token.pickle` inside the main repository directory.
3. Create a new `conf.py` file inside the main repository directory with [this content](#Config).
4. Do a `pip install -r requirements.txt` inside the main repository directory.
5. Run `python GMSync.py -i`

## All sync commands

Usage:

```bash
python GMSync.py [arguments]
```

| Argument | Description                                                                              |
| :------- | :--------------------------------------------------------------------------------------- |
| `-i`     | Database rebuild (interactive) and full sync                                             |
| `-d`     | Delta sync (unattended)                                                                  |
| `-f`     | Full sync (unattended)                                                                   |
| `-sb`    | Sync back new Monica contacts (unattended). Can be combined with all other arguments     |
| `-c`     | Check syncing database for errors (unattended). Can be combined with all other arguments |

Remark:
Full sync, database check and sync back require heavy API use (e.g. fetching of all Monica and Google contacts). So use wisely and consider the load you're producing with those operations (especially if you use the public hosted Monica instance).

## How it works

At first, the script builds an SQLite syncing database named `syncState.db`. To do that it fetches
all Google contacts and all Monica contacts (can take some time) and tries to match them by name.
If there is ambiguity you will be asked whether to link an existing contact or create a new one at Monica. The following details will be stored in the database file:

- Google contact ID (unique)
- Monica contact ID (unique)
- Google display name
- Monica complete name
- Google last updated timestamp
- Monica last changed timestamp
- Google delta sync token
- Google delta sync token timestamp

After building the database, full sync starts. This sync merges every Google and Monica contact according to the sync database and updates it on Monica *if necessary*. Name and birthday will be overwritten by the Google data, the deceased date will be preserved. Full sync also requests a sync token from Google that is used for every following delta sync.

Delta sync is only different from full sync in two points:

- The list of returned contacts from Googly (using the sync token) contains only changed contacts, so the sync will be faster
- It can detect deleted contacts from Google and delete them on Monica

If chosen, sync back will run after a sync or standalone (if no sync was selected). To find new contacts, the script will fetch all Monica contacts and search the database if they are already known. For all unknown ones, it will create a new Google contact and update the sync database accordingly. The new contact will then be included in every following normal sync.

All progress will be printed at running time and will be logged in the `Sync.log` file. If there are any errors at running time the sync will be aborted. Note that there is then a chance for an inconsistent database which you can check using `-c`. At the end the script will print some sync statistics.

## Database check

If you think something has gone wrong, you miss some contacts or just want a pretty database statistic, you can do a database check. This will check if every Google contact has its Monica counterpart and vice versa. It will also report orphaned database entries that do not have a contact on both sides.

## Config

This is the config file.
Copy the content below and create a new `conf.py` file inside the main repository directory.
Then fill in your desired settings (hint: a Monica token can be retrieved in your account settings, no OAuth client needed).

```python
# General: 
# String values need to be in single or double quotes
# Boolean values need to be True or False
# List Elements need to be are seperated by commas (e.g. ["a", "b"])

# Your Monica api token (without 'Bearer ')
TOKEN = 'YOUR_TOKEN_HERE'
# Your Monica base url
BASE_URL = 'https://app.monicahq.com/api'
# Create reminders for birthdays and deceased days?
CREATE_REMINDERS = True
# Delete Monica contact if the corresponding Google contact has been deleted?
DELETE_ON_SYNC = True
# Do a street reversal in address sync if the first character is a number? 
# (e.g. from '13 Auenweg' to 'Auenweg 13')
STREET_REVERSAL = False

# What fields should be synced? (both directions)
# Names and birthday are mandatory
FIELDS = {
    "career": True,     # Company and job title
    "address": True,
    "phone": True,
    "email": True,
    "labels": True,
    "notes": True
}

# Define contact labels/tags/groups you want to include or exclude from sync. 
# Exclude labels have the higher priority.
# Both lists empty means every contact is included
# Example: "include": ["Family"] will only process contacts labeled as Family.
GOOGLE_LABELS = {
    # Applies for Google -> Monica sync
    "include": [],
    "exclude": []
}
MONICA_LABELS = {
    # Applies for Monica -> Google sync back
    "include": [],
    "exclude": []
}
```

## Feature roadmap

- ~~Add more sync fields:~~
  - [x] company and job title
  - [x] labels
  - [x] address
  - [x] phone numbers
  - [x] emails
  - [x] notes
- ~~Add more sync-back fields:~~
  - [x] phone numbers
  - [x] emails
- [x] Implement a sync-back cmd-line switch for regularly sync-backs (not only on initial sync)
- [x] Maybe an additional (pretty printed) sync summary
- [x] Add sync include/exclude labels on both sides
- [x] Extend config to allow user choice of synced fields
- [ ] ~~Think about two-way sync~~ (too involving, not really needed)
- [x] Database consistency check function
- [ ] Think about a pip package
- [ ] Implement sync procedure using python threads (propably much faster with multithreading)
