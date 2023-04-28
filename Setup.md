[comment]: <> "LTeX: language=en-US"

# Google OAuth Application Setup Instructions

Use these instructions to set up API credentials for use with the syncing script.  
The following instructions are based on the [Create a project and enable the API](https://developers.google.com/workspace/guides/create-project) and [Create credentials](https://developers.google.com/workspace/guides/create-credentials) articles.

## Create a new Google Cloud Platform (GCP) project

To use the Google People API (formerly Contacts API), you need a Google Cloud Platform project. This project forms the basis for creating, enabling, and using all GCP services, including managing APIs, adding and removing collaborators, and managing permissions.

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Next to `Google Cloud Platform`, click the down arrow 🔽. A dialog listing current projects appears.
3. Click `New Project`. The New Project screen appears.
4. In the `Project Name` field, enter a descriptive name for your project. For example, enter "Google Monica Sync".
5. Click `Create`. The console navigates to the Dashboard page and your project is created within a few minutes.

## Enable the Google People API

1. Next to "Google Cloud Platform," click the down arrow 🔽 and open your newly created project.
2. In the top-left corner, click `Menu` > `APIs & Services`.
3. Click `Enable APIs and Services`. The `Welcome to API Library` page appears.
4. In the search field, enter `People API` and press enter.
5. Click `Google People API`. The API page appears.
6. Click `Enable`. The "Overview" page appears.

## Create credentials

Credentials are used to obtain an access token from a Google authorization server. This token is then used to call the Google People API. All Google Workspace APIs access data are owned by end-users.

### Configure the OAuth consent screen

The python script uses the OAuth protocol. When you start the script, it requests authorizations for `read/write contacts` from a Google Account. Google then displays a consent screen to you including a summary of your created project and the requested scopes of access. You must configure this consent screen for the authentication to work.

To configure the OAuth consent screen:

1. On the "Overview" page click `Credentials`. The credential page for your project appears.
2. Click `Configure Consent Screen`. The "OAuth consent screen" screen appears.
3. Select `External` as the user type for your app.
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
11. At the "Test user" section click `Add Users`, enter the email of the Google Account whose contacts you want to sync, and click `Add`.
    > Hint: If you get a `403 forbidden` during consent later, you may have entered the wrong email here.
12. Click `Save and Continue`. The "OAuth consent screen" appears.
13. Click `Back to Dashboard`.
14. Back at the "OAuth consent screen" screen, click `PUBLISH APP` and then `CONFIRM`.
    > This step is necessary because when in "Testing"-status, Google limits the token lifetime to seven days. You don't need to complete the app verification process.

### Create an OAuth client ID credential

1. In the left-hand navigation, click `Credentials`. The "Credentials" page appears.
2. Click `Create Credentials` and select `OAuth client ID`. The "Create OAuth client ID" page appears.
3. Click the Application type drop-down list and select "Desktop application".
4. In the name field, type a name for the credential. For example type "Python Syncing Script"
5. Click `Create`. The "OAuth client created" screen appears. This screen shows the Client ID and Client Secret.
6. Click `DOWNLOAD JSON`. This copies a client secret JSON file to your desktop. Note the location of this file.
7. Rename the client secret JSON file to `credentials.json`.

## Get the sync token and run initial sync (**without** docker)

0. Install Python 3.9 or newer
1. Copy `credentials.json` inside the `data` folder of the repository
2. In the main repository folder rename `.env.example` to `.env` and fill in your desired settings (a Monica token can be retrieved in your account settings).
3. Do a `pip install -r requirements.txt` inside the main repository directory.
4. Open a command prompt inside the main repository directory and run `python GMSync.py -i`.
5. On the first run the script will print a Google consent URL in the console. Copy this URL and open it in a browser on the host machine.
6. In your browser window, log in to your target Google account (the Google Account whose contacts you want to sync).
7. At "Google hasn’t verified this app" click `Continue`.
8. At "GMSync wants access to your Google Account" click `Continue`.
9. An authorization code should have been transmitted via local server, follow the prompts in your terminal to complete the initial sync.

## Get the sync token and run initial sync (**with** docker)

0. Install docker
1. In your chosen main folder, create two folders named `data` and `logs`.
2. Copy `credentials.json` inside a `data` folder of your main directory.
3. [Download](https://github.com/antonplagemann/GoogleMonicaSync/blob/main/.env.example) the `.env.example` file, rename to `.env`, put it in your main folder, and fill in your desired settings (a Monica token can be retrieved in your account settings).
    > This project is using a **non-root** container, so `data` and `logs` must have read-write permissions for UID 5678 (container user).
    > For example, you can use `sudo chown -R 5678 data logs` or `sudo chmod -R 777 data logs` inside your main directory to set the appropriate permissions.
4. Open a command prompt inside the main directory run initial sync using the following command (on Windows replace `$(pwd)` with `%cd%`)

    ```bash
    docker run -v "$(pwd)/data":/usr/app/data -v "$(pwd)/logs":/usr/app/logs -p 56411:56411 --env-file .env -it antonplagemann/google-monica-sync sh -c "python -u GMSync.py -i"
    ```

5. On the first run the script will print a Google consent URL in the console. Copy this URL and open it in a browser on the host machine.
6. In your browser window, log in to your target Google account (the Google Account whose contacts you want to sync).
7. At "Google hasn’t verified this app" click `Continue`.
8. At "GMSync wants access to your Google Account" click `Continue`.
9. An authorization code should have been transmitted via local server, follow the prompts in your terminal to complete the initial sync.
