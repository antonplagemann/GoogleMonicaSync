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