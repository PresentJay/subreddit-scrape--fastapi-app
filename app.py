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

# Get Reddit API token from environment variable
reddit_api_token = os.getenv("REDDIT_API_TOKEN")

# Get randomly picked one image URL in candidate amount
def getImgURL():
    # If you got an error or not an image, the bot will rescrape the target subreddit ${duration} times.
    duration = 5

    url = f"https://oauth.reddit.com/r/{subredditName}/hot.json?limit={fetchingAmount}"
    headers = {
        "Authorization": f"Bearer {reddit_api_token}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
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

    while duration >= 1:
        if "error" in json_data.keys():
            # For avoiding server ban raised by the same repetition time, it will be randomized in the real value of [0-1].
            duration -= 1
            sleep(random.random())
            continue
        imgURLlist = json_data["data"]["children"]
        selected = random.choice(imgURLlist)
        if selected["data"]["post_hint"] == "image":
            return selected["data"]["url"]

# Set given image streams to byte, downsizing, and return the file
# TODO: some images still raise an error to show in GitHub readme. I guess this is because of size or something.
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
