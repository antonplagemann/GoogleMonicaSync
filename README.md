[comment]: <> "LTeX: language=en-US"

# Google to Monica contact syncing script

🤖 Automated CI/CD Pipelines

[![CodeQL](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/codeql-analysis.yml)
[![Docker CD](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/docker-cd.yml/badge.svg)](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/docker-cd.yml)
[![Python CI](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/python-ci.yml/badge.svg)](https://github.com/antonplagemann/GoogleMonicaSync/actions/workflows/python_ci.yml)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![spellcheck: codespell](https://img.shields.io/badge/spellcheck-codespell-brightgreen.svg)](https://github.com/codespell-project/codespell)
[![security: bandit](https://img.shields.io/badge/security-bandit-success.svg)](https://github.com/PyCQA/bandit)
[![linter: flake8](https://img.shields.io/badge/linter-flake8-brightgreen.svg)](https://github.com/PyCQA/flake8)
[![imports: isort](https://img.shields.io/badge/imports-isort-blue.svg)](https://pycqa.github.io/isort/)
[![mypy: checked](https://img.shields.io/badge/mypy-checked-blue.svg)](https://github.com/python/mypy)

🔒 SonarCloud monitored

[![SonarCloud Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=bugs)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=antonplagemann_GoogleMonicaSync&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=antonplagemann_GoogleMonicaSync)

## Hey 👋

Using [Monica](https://github.com/monicahq/monica) and Google Contacts, but you're annoyed by keeping your data in sync? Then this python script is for you 😎  
It does one-way ➡ contact syncing of your Google Contacts to a Monica account 🎉  
But wait, before trying something new, please do not forget to **make a full backup 🔒** before entering the first command 😉  
I did my best to write clean and working code, but if I missed a bug 🐛 that you've found, please return it to me 🏡😊, I would be happy to fix it 🙏!  
All contributions are welcome! Feel free to open an issue or pull request 🙌

## Features

- One-way sync (Google → Monica)
  - Syncs the following details: first name, last name, middle name, nickname, birthday, job title, company, addresses, phone numbers, email addresses, labels (tags), notes (see [limits](#limits))
- Advanced matching of already present Monica contacts (e.g. from earlier contact import)
- User choice prompt before any modification to your Monica data during initial sync (you can choose to abort before the script makes any change)
- Fast delta sync using Google sync tokens
- Optional sync-back (Monica → Google) of new Monica contacts that do not have a corresponding Google contact yet
  - Syncs the following details: first name, last name, middle name, birthday, job title, company, addresses, phone numbers, email addresses, labels (tags)
- Extensive logging of every change, warning, or error including the affected contact ID and name (file: `logs/sync.log`)

## Limits

- **Do not update [*synced*](#features) details at Monica.** As this is a one-way ➡ sync, it will overwrite all Monica changes to these fields! Of course, you can continue to use activities, notes, journal, relationships and almost any other Monica feature. Just don't update [name, birthday, job info, ...](#features) at Monica.
- **Do not delete synced contacts at Monica.** This will cause a sync error which you can resolve by doing initial sync again.
- The Monica public instance limits API usage to 60 calls per minute. As every contact needs *at least* 2 API calls, **the script can not sync more than 30 contacts per minute** (thus affecting primarily initial and full sync).  
    > If you are using the hosted version of Monica you can [configure this rate limit](https://github.com/monicahq/monica/pull/5489) starting from Monica v3.3.0.
- Delta sync will fail if there are more than 7 days between the last sync (Google restriction). In this case, the script will automatically do (fast) full sync instead
- A label itself won't be deleted automatically if it has been removed from the last contact.
- If there is a Google note it will be synced with exactly one Monica note. To this end, a small text will be added to the synced note at Monica. This makes it easy for you to distinguish synced and Monica-only notes. This means **you can update and create as many *additional* notes as you want at Monica**, they will not be overwritten.
- Monica contacts require a first name. If a Google contact does not have any name, it will be skipped.

## Known bugs

- Sometimes the Google API returns more contacts than necessary. This is not an issue because the sync will match the last known update timestamps and skip the contact if nothing has changed.
- Birthdays on 29. Feb will be synced as 01. March 😊
- Pay attention when you *merge* Google contacts on the web GUI. In this case the contact will get recreated at Monica during sync if `DELETE_ON_SYNC` is set to `True` (default: `False`), because Google assigns a new contact ID. That means all Monica-specific data will be deleted. You can avoid this by merging them manually (copy over the details by hand) or doing initial sync `-i` again afterwards.

## Get started

The setup is a bit involving process as you have to create a Google Cloud Platform project to access your contacts via the Google People API.  
[Please follow this guide](./Setup.md) to complete the required steps and do an initial sync. Once you did that you can use one of the delta sync commands from the next section to update your contacts regularly.

## Delta sync (without docker)

Run the following command inside the main folder:

```bash
python GMSync.py -d
```

## Delta sync (with docker)

For delta sync use this command:

```bash
docker run -v "$(pwd)/data":/usr/app/data -v "$(pwd)/logs":/usr/app/logs --env-file .env antonplagemann/google-monica-sync sh -c "python -u GMSync.py -d"
```

Alternatively to step 5 you can download and configure the [docker-compose.yml](https://github.com/antonplagemann/GoogleMonicaSync/blob/main/docker-compose.yml) to your main directory and use `docker-compose up` (Windows & Linux).

### Background script with docker

Here's a sample script which can use to automate syncing e.g. with a crontab schedule.

```bash
#!/bin/bash

cd /path/to/folder-with-docker-compose-yaml
set -e
export COMPOSE_INTERACTIVE_NO_CLI=1
docker-compose up -d
```

## All commands

Usage:

```bash
python GMSync.py [arguments]
```

| Argument  | Description                                                                              |
| :-------- | :--------------------------------------------------------------------------------------- |
| `-i`      | Database rebuild (interactive) and full sync                                             |
| `-d`      | Delta sync (unattended)                                                                  |
| `-f`      | Full sync (unattended)                                                                   |
| `-sb`     | Sync back new Monica contacts (unattended). Can be combined with all other arguments     |
| `-c`      | Check syncing database for errors (unattended). Can be combined with all other arguments |
| `-e PATH` | Custom .env configuration file path (relative or absolute)                               |

**Remark**:  
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

After building the database, full sync starts. This sync merges every Google and Monica contact according to the sync database and updates it on Monica *if necessary*. Full sync also requests a sync token from Google that is used for every following delta sync.

Delta sync is only different from full sync in two points:

- The list of returned contacts from Googly (using the sync token) contains only changed contacts, so the sync will be faster
- It *can* detect deleted contacts from Google and delete them on Monica

If chosen, sync back will run after a sync or standalone (if no other sync is selected). To find new contacts, the script will fetch all Monica contacts and search the database if they are already known. For all unknown ones, it will create a new Google contact and update the sync database accordingly. The new contact will then be included in every following full or delta sync.

All progress will be printed at running time and logged in the `Sync.log` file. If there are any errors, the sync will be aborted. Note that there is then a chance for an inconsistent database which you can check using `-c`. At the end the script will print some sync statistics.

## Database check

If you think something has gone wrong, you miss some contacts or just want a pretty database statistic, you can do a database check. This will check if every Google contact has its Monica counterpart and vice versa. It will also report orphaned database entries that do not have a contact on both sides.

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
- [ ] ~~Think about a pip package~~
- [ ] ~~Implement sync procedure using python threads: probably much faster with multithreading~~ (not much faster because the Monica API rate limit is the bottleneck here)
- [x] Add docker container
- [x] Add automated testing of changes
