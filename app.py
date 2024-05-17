import random
import os
import requests
import json
from flask import Flask, send_file
from PIL import Image
from io import BytesIO

app = Flask(__name__)

# Get Reddit API credentials from environment variables
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")

if not all([client_id, client_secret, username, password]):
    raise ValueError("Please set all required environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")

# Authenticate and get access token
def get_access_token():
    url = "https://www.reddit.com/api/v1/access_token"
    data = {
        "grant_type": "password",
        "username": username,
        "password": password
    }
    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    response = requests.post(url, data=data, auth=auth, headers={"User-Agent": "Reddit Image Scraper"})
    response_data = response.json()
    if response.status_code == 200:
        return response_data.get("access_token")
    else:
        raise ValueError(f"Failed to get access token: {response_data.get('error_description')}")

# Get randomly picked one image URL in candidate amount
def get_img_url():
    access_token = get_access_token()
    url = f"https://oauth.reddit.com/r/programmerhumor/hot.json?limit=100"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Reddit Image Scraper"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    children = data.get("data", {}).get("children", [])
    image_posts = [post["data"]["url"] for post in children if post.get("data", {}).get("post_hint") == "image"]
    return random.choice(image_posts)

# Set given image streams to byte, downsizing, and return the file
def serve_pil_image(pil_img, content_type):
    img_io = BytesIO()
    pil_img.save(img_io, format="JPEG")
    img_io.seek(0)
    return send_file(img_io, mimetype=content_type)

@app.route("/", methods=["GET"])
def return_meme():
    img_url = get_img_url()
    response = requests.get(img_url, stream=True)
    response.raise_for_status()
    content_type = response.headers["Content-Type"]
    image = Image.open(BytesIO(response.content))
    return serve_pil_image(image, content_type)

if __name__ == "__main__":
    app.run()
