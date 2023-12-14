import random
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

SUBREDDIT_NAME = "ProgrammerHumor"
FETCHING_AMOUNT = 99

def get_image_url():
    retries = 5
    url = f"https://www.reddit.com/r/{SUBREDDIT_NAME}.json?limit={FETCHING_AMOUNT}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:20.0) Gecko/20100101 Firefox/20.0'}

    while retries > 0:
        response = requests.get(url=url, headers=headers)

        if response.status_code == 404:
            app.logger.warning("Received 404 error. Retrying...")
            retries -= 1
            sleep(random.random())
            continue

        try:
            json_data = response.json()
        except json.decoder.JSONDecodeError as e:
            app.logger.warning(f"Invalid JSON received. Error: {e}. Retrying...")
            retries -= 1
            sleep(random.random())
            continue

        children = json_data.get("data", {}).get("children", [])
        if not children:
            app.logger.warning("No image URLs found. Retrying...")
            retries -= 1
            sleep(random.random())
            continue

        selected = random.choice(children)
        if selected.get("data", {}).get("post_hint") == "image":
            img_url = selected["data"]["url"]
            app.logger.info(f"Selected image URL: {img_url}")
            return img_url

    return None

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

    if img_url:
        response = requests.get(img_url, stream=True)

        if response.status_code == 200:
            content_type = response.raw.headers["Content-Type"]
            response.raw.decode_content = True
            img = Image.open(response.raw)
            return serve_pil_image(img, content_type)

    return "Error: Unable to fetch a valid image", 500

if __name__ == "__main__":
    app.run(debug=True)
