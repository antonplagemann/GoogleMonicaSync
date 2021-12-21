[comment]: <> "LTeX: language=en-US"

# Google OAuth Application Setup Instructions

Use these instructions to set up API credentials for the use with the syncing script.
The following instructions are based on the [`Create a project and enable the API`](https://developers.google.com/workspace/guides/create-project) article and [`Create credentials`](https://developers.google.com/workspace/guides/create-credentials) article.

## Create a new Google Cloud Platform (GCP) project

To use the Google People API (formerly Contacts API), you need a Google Cloud Platform project. This project forms the basis for creating, enabling, and using all GCP services, including managing APIs, enabling billing, adding and removing collaborators, and managing permissions.

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Next to `Google Cloud Platform`, click the down arrow 🔽. A dialog listing current projects appears.
3. Click `New Project`. The New Project screen appears.
4. In the `Project Name` field, enter a descriptive name for your project. For example enter "Google Monica Sync".
5. Click `Create`. The console navigates to the Dashboard page and your project is created within a few minutes.

## Enable a Google People API

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Next to "Google Cloud Platform," click the down arrow 🔽 and open your newly created project.
3. In the top-left corner, click `Menu` > `APIs & Services`.
4. Click `Enable APIs and Services`. The `Welcome to API Library` page appears.
5. In the search field, enter `People API` and press enter.
6. Click `Google People API`. The API page appears.
7. Click `Enable`. The "Overview" page appears.

## Create credentials

Credentials are used to obtain an access token from a Google authorization server. This token is used to call the Google People API. All Google Workspace APIs access data owned by an end-user.

### Configure the OAuth consent screen

When you use OAuth 2.0 for authorization, your app requests authorizations for one or more scopes of access from a Google Account. Google displays a consent screen to the user including a summary of your project and its policies and the requested scopes of access. You must configure the consent screen for all apps. However, you need only list scopes used by your app for external apps.

To configure the OAuth consent screen:

1. On the "Overview" page click `Credentials`. The credential page for your project appears.
2. Click `Configure Consent Screen`. The "OAuth consent screen" screen appears.
3. Select `External` as user type for your app.
4. Click `Create`. A second "OAuth consent screen" screen appears.
5. Fill out the required form field (leave others blank):
        - Enter "GMSync" in the `App name` field.
        - Enter your personal email address in the `User support email` field.
        - Enter your personal email address in the `Developer contact information` field.
6. Click `Save and Continue`. The "Scopes" page appears.
7. Click `Add or Remove Scopes`. The "Update selected scopes" page appears.
8. Filter for "People API" and select the scope ".../auth/contacts".
9. Click `Update`. A list of scopes for your app appears. Check if the scope ".../auth/contacts" is now listed in "Your sensitive scopes".
10. Click `Save and Continue`. The "Edit app registration" page appears.
11. At the "Test user" section click `Add Users`, enter the email of the Google Account whose contacts you want to sync and click `Add`. Hint: If you get a `403 forbidden` during consent later, you may have entered the wrong email here.
12. Click `Save and Continue`. The "OAuth consent screen" appears.
13. Click `Back to Dashboard`.

### Create a OAuth client ID credential

1. In the left-hand navigation, click `Credentials`. The "Credentials" page appears.
2. Click `Create Credentials` and select `OAuth client ID`. The "Create OAuth client ID" page appears.
3. Click the Application type drop-down list and select "Desktop application".
4. In the name field, type a name for the credential. For example type "Python Syncing Script"
5. Click `Create`. The OAuth client created screen appears. This screen shows the Client ID and Client secret.
6. Click `DOWNLOAD JSON`. This copies a client secret JSON file to your desktop. Note the location of this file.
7. Rename the client secret JSON file to `credentials.json`.

## Get the sync token and run initial sync (**without** docker)

1. Copy `credentials.json` inside the `data` folder of the repository
2. In the main repository folder rename `.env.example` to `.env` and fill in your desired settings (a Monica token can be retrieved in your account settings).
3. Do a `pip install -r requirements.txt` inside the main repository directory.
4. Open a command prompt inside the main repository directory and run `python GMSync.py -i`.
5. On the first run the script will print a Google consent URL in the console. Copy this URL and open it in a browser on the host machine.
6. In your browser window, log in into your target Google account (the Google Account whose contacts you want to sync).
7. At "Google hasn’t verified this app" click `Continue`.
8. At "GMSync wants access to your Google Account" click `Continue`.
9. You should see now an authorization code. Copy this code, and switch back to your terminal window.
10. Paste the authorization code, press enter and follow the prompts to complete initial sync.

## Get the sync token and run initial sync (**with** docker)

1. In your chosen main folder, create two folders named `data` and `logs`.
2. Copy `credentials.json` inside a `data` folder of your main directory.
3. [Download](https://github.com/antonplagemann/GoogleMonicaSync/blob/main/.env.example) the `.env.example` file, rename to `.env`, put it in your main folder and fill in your desired settings (a Monica token can be retrieved in your account settings).
    > This project is using a **non-root** container, so `data` and `logs` must have read-write permissions for UID 5678 (container user).
    > For example, you can use `sudo chown 5678 data logs` inside your main directory to set the appropriate permissions. Sometimes this may be also necessary for files inside those folders (if you get a `permission denied` error).
4. Open a command prompt inside the main directory run initial sync using the following command (on Windows replace `$(pwd)` with `%cd%`)

    ```bash
    docker run -v "$(pwd)/data":/usr/app/data -v "$(pwd)/logs":/usr/app/logs --env-file .env -it antonplagemann/google-monica-sync sh -c "python -u GMSync.py -i"
    ```

5. On the first run the script will print a Google consent URL in the console. Copy this URL and open it in a browser on the host machine.
6. In your browser window, log in into your target Google account (the Google Account whose contacts you want to sync).
7. At "Google hasn’t verified this app" click `Continue`.
8. At "GMSync wants access to your Google Account" click `Continue`.
9. You should see now an authorization code. Copy this code, and switch back to your terminal window.
10. Paste the authorization code, press enter and follow the prompts to complete initial sync.