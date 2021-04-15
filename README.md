# Google to Monica contact syncing script

## Introduction

This script does a contact syncing from a Google account to a [Monica](https://github.com/monicahq/monica) account. This script is intended for personal use only. It can contain a lot of bugs, errors, and unhandled exceptions, so do a backup before using it. It was programmed very carefully not to screw things up and delete everything but it`s your own risk trusting my words.

That being said: Be welcome to use it, fork and develop it, copy it for your projects, and file issues for bug fixes or improvements you wish for.

## Features

- One-way sync (Google -> Monica)
  - Syncs the following details: first name, last name, middle name, birthday, job title, company, addresses, phone numbers, email addresses, labels (tags), note (add only, see [limits](#limits))
- Advanced matching of already present Monica contacts (e.g. from earlier contact import)
- Fast delta sync using Google sync tokens
- Optional sync-back (Monica -> Google) of new Monica contacts that do not have a corresponding Google contact yet
  - Syncs the following details: first name, last name, middle name, birthday, company, job title, labels (tags), addresses
- Extensive logging of every change, warning, or error including the affected contact ids and names (File: `Sync.log`)

## Limits

- **Do not update [*synced*](#features) details at Monica.** As this is a one-way sync, it will overwrite all Monica changes to this fields! Of course you can continue to use activities, notes, journal, relationships and almost any other Monica feature. Just don't update [name, birthday, job info, ...](#features) at Monica.
- **Do not delete contacts at Monica.** This will cause a sync error which you can resolve by doing initial sync again.
- Delta sync will fail if there are more than 7 days between the last sync (Google restriction). In this case, the script will automatically do full sync instead
- No support for custom Monica gender types. Will be overwritten with standard type O (other)
- A label itself won't be deleted automatically if it has been removed from the last contact
- A Google contact note will *only* be synced *once* if there are no notes already in the corresponding Monica contact. This means **you can update and create as many notes as you want at Monica**, they will not be overwritten.

## Known bugs

- I observed strange behavior of the Google sync tokens used for delta sync. Sometimes the response contains the same sync token as before but includes a lot of updated contacts. Often the response contains more updated contacts than I should (I haven't changed that many). This is not an issue because the sync will count on the `updateTime` timestamp which seems more reliable. It will match them against the database timestamp and skip the contact if it is equal.
- Birthdays on 29. Feb will be synced as 01. March :-)

## Get started

1. Get the [official Python Quickstart script from Google](https://developers.google.com/people/quickstart/python) working.
2. Copy `credentials.json` and `token.pickle` inside the main repository directory.
3. [Download](https://github.com/antonplagemann/GoogleMonicaSync/blob/90c8d8749d0291e828e8c8b50a143efe636c73f3/conf.py) the `conf.py` file, fill in your desired settings and copy it inside the main directory (hint: a Monica token can be retrieved in your account settings, no Oauth client needed).
4. Do a `pip install -r requirements.txt` inside the main repository directory.
5. Run `python GMSync.py -i`

## All sync commands

Usage:

```bash
python GMSync.py [arguments]
```

| Argument | Description                                                                          |
| :------- | :----------------------------------------------------------------------------------- |
| `-i`     | Database rebuild (interactive) and full sync                                         |
| `-d`     | Delta sync (unattended)                                                              |
| `-f`     | Full sync (unattended)                                                               |
| `-sb`    | Sync back new Monica contacts (unattended). Can be combined with all other arguments |

Remark:
Full sync and sync back require heavy api use (e.g. fetching of all Monica and Google contacts). So use wisely and consider the load you're producing with those operations (especially if you use the public hosted Monica instance).

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

After building the database, full sync starts. This sync merges every Google and Monica contact according to the sync database and updates it on Monica *if neccessary*. Name and birthday will be overwritten by the Google data, the deceased date will be preserved. Full sync also requests a sync token from Google that is used for every following delta sync. Delta sync is only different from full sync in two points:

- The list of returned contacts from Googly (using the sync token) contains only changed contacts, so the sync will be faster
- It can detect deleted contacts from Google and delete them on Monica

If chosen, sync back will run after a sync or standalone (if no sync was selected). To find new contacts, the script will fetch all Monica contacts and search the database if they are already known. For all unknown ones, it will create a new Google contact and update the sync database accordingly.

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
# Delete Monica contact if the corresponding Google contact has been deleted?
DELETE_ON_SYNC = True
# Do a street reversal in address sync if the first character is a number.
# E.g. from '13 Auenweg' to 'Auenweg 13'
STREET_REVERSAL = False
```

## Feature roadmap (working on it)

- Add more sync fields:
  - [x] company and jobtitle
  - [x] labels
  - [x] address
  - [x] phone numbers
  - [x] emails
  - [x] notes
- Add more sync-back fields:
  - [ ] phone numbers
  - [ ] emails
- [x] Implement a sync-back cmd-line switch for regularily sync-backs (not only on initial sync)
- [ ] Database consistency check function
- [ ] Maybe an additional (pretty printed) sync summary
- [ ] Implement sync procedure using python threads (propably much more faster)
- [ ] Add sync include/exclude labels on both sides
- [ ] ~~Think about two-way sync~~ (too involving, not really needed)
- [ ] Think about a pip package
- [ ] Extend config to allow user choice of synced fields? (not sure if this is needed)
