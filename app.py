import json
import logging
import random
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

# Constants
SUBREDDIT_NAME = "ProgrammerHumor"
FETCHING_AMOUNT = 99

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_image_url():
    duration = 5
    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}.json?limit={FETCHING_AMOUNT}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:20.0) Gecko/20100101 Firefox/20.0'}
    
    while duration >= 1:
        req = requests.get(url=url, headers=headers)
        try:
            json_data = req.json()
        except json.decoder.JSONDecodeError:
            logger.warning("Invalid JSON received. Retrying...")
            duration -= 1
            sleep(random.random())
            continue

        if "error" in json_data.get("data", {}).get("children", []):
            logger.warning("Error in response. Retrying...")
            duration -= 1
            sleep(random.random())
            continue

        img_url_list = json_data.get("data", {}).get("children", [])
        selected = random.choice(img_url_list)
        if selected.get("data", {}).get("post_hint") == "image":
            return selected["data"]["url"]

def serve_pil_image(pil_img, content_type):
    img_io = BytesIO()
    pil_img.save(img_io, content_type.split('/').pop(), quality=70)
    img_io.seek(0)
    return send_file(img_io, mimetype=content_type)

@app.after_request
def set_response_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/", methods=['GET'])
def return_meme():
    img_url = get_image_url()

    if img_url is None:
        # Handle the case where no valid image URL is found
        return "No valid image found", 404  # You can customize this response as needed

    res = requests.get(img_url, stream=True)

    if res.status_code != 200:
        # Handle the case where the image request is unsuccessful
        return f"Error fetching image: {res.status_code}", 500  # You can customize this response as needed

    # set MIME type as scraped image MIME (jpeg, png, gif ...)
    content_type = res.headers.get("Content-Type", "image/jpeg")

    res.raw.decode_content = True
    img = Image.open(res.raw)
    return serve_pil_image(img, content_type)

if __name__ == "__main__":
    app.run(debug=True)
