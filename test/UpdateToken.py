import os
from base64 import b64encode

import requests
from nacl import encoding, public  # type: ignore

REPO = os.getenv("GITHUB_REPOSITORY")
SECRET_NAME = "GOOGLE_TOKEN"  # nosec
REPO_TOKEN = os.getenv("REPO_TOKEN")


def encrypt(public_key: str, secret_value: str) -> str:
    """Encrypt a Unicode string using the public key."""
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


# Read token
with open("data/token.pickle", "r") as base64_token:
    creds_base64 = base64_token.read()

# Get repo public key
headers = {"accept": "application/vnd.github.v3+json", "Authorization": f"token {REPO_TOKEN}"}
response = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=headers, timeout=5
)
response.raise_for_status()
data = response.json()
public_key_id: str = data["key_id"]
public_key: str = data["key"]

# Encrypt secret
encrypted_secret = encrypt(public_key, creds_base64)
body = {"encrypted_value": encrypted_secret, "key_id": public_key_id}

# Set secret
response = requests.put(
    f"https://api.github.com/repos/{REPO}/actions/secrets/{SECRET_NAME}",
    headers=headers,
    json=body,
    timeout=5,
)
response.raise_for_status()
