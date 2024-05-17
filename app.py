import random
import os
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

# Set subreddit name
subredditName = "programmerhumor"

# Set scraping candidate amount in subreddit once
fetchingAmount = 99

# Get Reddit API credentials from environment variables
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")

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
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print(f"Error: {response.status_code}")
        print(response.content)
        return None


# Get randomly picked one image URL in candidate amount
def getImgURL():
    access_token = get_access_token()
    url = f"https://oauth.reddit.com/r/{subredditName}/hot.json?limit={fetchingAmount}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Reddit Image Scraper"
    }
    req = requests.get(url=url, headers=headers)
    if req.status_code == 200:
        try:
            json_data = req.json()
        except json.decoder.JSONDecodeError as e:
            print(f"JSON decoding error: {e}")
    else:
        print(f"Error: {req.status_code}")

    print(req.content)

    imgURLlist = json_data["data"]["children"]
    selected = random.choice(imgURLlist)
    if selected["data"]["post_hint"] == "image":
        return selected["data"]["url"]

# Set given image streams to byte, downsizing, and return the file
def serve_pil_image(pil_img, contentType):
    img_io = BytesIO()
    pil_img.save(img_io, contentType.split("/").pop(), quality=70)
    img_io.seek(0)
    return send_file(img_io, mimetype=contentType)


@app.after_request
def set_response_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Set Flask routes in root to get image file
@app.route("/", methods=["GET"])
def return_meme():
    img_url = getImgURL()
    res = requests.get(img_url, stream=True)

    # Set MIME type as scraped image MIME (jpeg, png, gif...)
    contentType = res.headers["Content-Type"]

    res.raw.decode_content = True
    img = Image.open(res.raw)
    return serve_pil_image(img, contentType)
