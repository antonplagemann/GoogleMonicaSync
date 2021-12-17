"""Gets an API token from a new Monica instance"""

import logging
import os
from os.path import join
from time import sleep
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup  # type: ignore
from requests import ConnectionError, ConnectTimeout, ReadTimeout

LOG_FOLDER = "logs"
LOG_FILENAME = "setup.log"
HOST = "localhost"

# Set logging configuration
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)
log = logging.getLogger("setup")
log.setLevel(logging.INFO)
logging_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
log_filepath = join(LOG_FOLDER, LOG_FILENAME)
handler = logging.FileHandler(filename=log_filepath, mode="a", encoding="utf8")
handler.setLevel(logging.INFO)
handler.setFormatter(logging_format)
log.addHandler(handler)
msg = "Script started"
log.info(msg)
print(msg)

try:
    # Wait for Monica to be ready
    msg = "Waiting for Monica to get ready"
    log.info(msg)
    print(msg)
    waiting_time = 0
    max_time = 300  # Wait max. 5 minutes
    while True:
        try:
            response = requests.get(f"http://{HOST}:8080/register", timeout=0.2)
            if response.status_code == 200:
                msg = f"Ready after {waiting_time} seconds"
                print(msg)
                log.info(msg)
                sleep(1)
                break
        except (ConnectTimeout, ConnectionError, ReadTimeout):
            waiting_time += 1
            sleep(0.8)
            if waiting_time > max_time:
                raise TimeoutError(f"Waiting time ({max_time} seconds) exceeded!")
            print(f"Waiting for Monica: {max_time - waiting_time} seconds remaining")

    # Get register token
    msg = "Fetching register page"
    log.info(msg)
    print(msg)
    response = requests.get(f"http://{HOST}:8080/register")
    response.raise_for_status()
    cookies = response.cookies
    soup = BeautifulSoup(response.text, "html.parser")
    inputs = soup.find_all("input")
    token = [
        input_tag["value"] for input_tag in soup.find_all("input") if input_tag.get("name") == "_token"
    ][0]

    # Register new user
    data = {
        "_token": token,
        "email": "some.user@email.com",
        "first_name": "Some",
        "last_name": "User",
        "password": "0JS65^Pp%kFyQh1q5vPx7Mzcj",
        "password_confirmation": "0JS65^Pp%kFyQh1q5vPx7Mzcj",
        "policy": "policy",
        "lang": "en",
    }
    msg = "Registering new user"
    log.info(msg)
    print(msg)
    response = requests.post(f"http://{HOST}:8080/register", cookies=response.cookies, data=data)
    response.raise_for_status()

    # Create api token
    headers = {
        "X-XSRF-TOKEN": unquote(response.cookies.get("XSRF-TOKEN")),
    }
    data = {"name": "PythonTestToken", "scopes": [], "errors": []}
    msg = "Requesting access token"
    log.info(msg)
    print(msg)
    response = requests.post(
        f"http://{HOST}:8080/oauth/personal-access-tokens",
        headers=headers,
        cookies=response.cookies,
        json=data,
    )
    response.raise_for_status()

    # Extract token from response
    access_token = response.json().get("accessToken", "error")

    # Save token to environment
    env_file = os.getenv("GITHUB_ENV", ".env")
    print(f"Saving access token to '{env_file}'")
    log.info(f"Saving access token '{access_token}' to '{env_file}'")
    with open(env_file, "a") as myfile:
        myfile.write(f"TOKEN={access_token}\n")

    msg = "Script finished"
    log.info(msg)
    print(msg)

except Exception as e:
    log.exception(e)
    log.info("Script aborted")
    print(f"\nScript aborted: {type(e).__name__}: {str(e)}")
    print(f"See log file ({join(LOG_FOLDER, LOG_FILENAME)}) for all details")
    raise SystemExit(1) from e
