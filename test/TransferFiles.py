"""Transfers files from and to Azure Blob Storage"""

import argparse
import logging
import os
from os.path import join
from posixpath import join as posix_join
from urllib.parse import unquote
from typing import List

from azure.storage.blob import BlobServiceClient  # type: ignore

LOG_FOLDER = "logs"
LOG_FILENAME = "transfer.log"
CONTAINER = "gmsync"

# Set logging configuration
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)
log = logging.getLogger("azure.storage.blob")
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

    # Setup argument parser
    parser = argparse.ArgumentParser(description="Transfers file to Azure Blob Storage")

    parser.add_argument(
        "-f",
        "--files",
        type=str,
        nargs="+",
        help="The files.txt or folders/ to up or download",
        required=True,
    )
    parser.add_argument(
        "-t", "--token", type=str, required=False, help="The SAS token for Azure Blob Storage"
    )
    parser.add_argument(
        "-a",
        "--account-url",
        type=str,
        required=False,
        help="The destination account url for Azure Blob Storage",
    )
    parser.add_argument(
        "-u",
        "--upload",
        action="store_true",
        required=False,
        help="Uploads the specified file",
    )
    parser.add_argument(
        "-d",
        "--download",
        action="store_true",
        required=False,
        help="Downloads the specified file",
    )

    # Parse arguments
    args = parser.parse_args()

    # Get token, account url and filename (these GitHub secrets need to be urlencoded)
    AZURE_TOKEN: str = unquote(os.environ.get("AZURE_TOKEN", args.token))
    ACCOUNT_URL: str = unquote(os.environ.get("ACCOUNT_URL", args.account_url))
    TARGETS: List[str] = args.files

    # Create clients
    msg = "Creating service client"
    log.info(msg)
    print(msg)
    service = BlobServiceClient(account_url=ACCOUNT_URL, credential=AZURE_TOKEN, logging_enable=True)

    files = []

    if args.upload:
        # Get list of all files
        for entry in TARGETS:
            if os.path.isdir(entry):
                files += [posix_join(dp, f) for dp, _, filenames in os.walk(entry) for f in filenames]
            elif os.path.isfile(entry):
                files.append(entry)
            else:
                log.warning(f"Target file '{entry}' not found!")

        # Upload files
        for filename in files:
            blob = service.get_blob_client(container=CONTAINER, blob=filename)
            with open(filename, "rb") as data:
                blob.upload_blob(data, overwrite=True)
            msg = f"Uploaded '{filename}' to '{CONTAINER}'"
            log.info(msg)
            print(msg)

    elif args.download:
        # Get list of all blob files
        container = service.get_container_client(container=CONTAINER)
        blob_list = list(container.list_blobs())
        # Split targets into files and folders
        target_files = [entry for entry in TARGETS if not entry.endswith("/")]
        target_folders = [entry for entry in TARGETS if entry.endswith("/")]
        # Search target files in blob storage
        for target_file in target_files:
            results = [entry.name for entry in blob_list if entry.name == target_file]
            if not results:
                log.warning(f"Target file '{target_file}' not found!")
            files += results
        # Search target folders in blob storage
        for target_folder in target_folders:
            results = [
                entry.name
                for entry in blob_list
                for folder in target_folders
                if "/" in entry.name and entry.name.startswith(folder)
            ]
            if not results:
                log.warning(f"Target folder '{target_folder}' not found!")
            files += results

        # Download files
        for filename in files:
            blob = service.get_blob_client(container=CONTAINER, blob=filename)
            with open(filename, "wb") as my_blob:
                blob_data = blob.download_blob()
                blob_data.readinto(my_blob)
            msg = f"Downloaded '{filename}' from '{CONTAINER}'"
            log.info(msg)
            print(msg)

    else:
        log.error("Please specify either up or download!")

    msg = "Script finished"
    log.info(msg)
    print(msg)

except Exception as e:
    log.exception(e)
    log.info("Script aborted")
    print(f"\nScript aborted: {type(e).__name__}: {str(e)}")
    print(f"See log file ({join(LOG_FOLDER, LOG_FILENAME)}) for all details")
    raise SystemExit(1) from e
