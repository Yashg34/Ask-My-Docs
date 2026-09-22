import requests
import os

api_key = "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"
url = "https://api.groq.com/openai/v1/models"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

response = requests.get(url, headers=headers)

print(response.json())