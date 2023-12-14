import random
import requests
from flask import Flask, send_file, after_request
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

# Set subreddit name
subreddit_name = "ProgrammerHumor"

# Set scraping candidate amount in subreddit once
fetching_amount = 99

# Get randomly picked one image URL in candidate amount.
def get_img_url():
    # If you encounter an error or not an image, the bot will rescrape the target subreddit ${duration} times.
    duration = 5
    
    url = f"https://www.reddit.com/r/{subreddit_name}.json?limit={fetching_amount}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:20.0) Gecko/20100101 Firefox/20.0'}
    
    while duration >= 1:
        req = requests.get(url=url, headers=headers)
        json_data = req.json()
        
        if "error" in json_data:
            # For avoiding server ban raised by the same repetition time, it will be randomized in the real value of [0-1].
            duration -= 1
            sleep(random.random())
            continue
        
        img_url_list = json_data["data"]["children"]
        selected = random.choice(img_url_list)
        
        if selected["data"]["post_hint"] == "image":
            return selected["data"]["url"]

# Set given image streams to byte, downsizing, and return to file.
# TODO: Some images still raise an error to show in the GitHub readme. I guess this is because of size or something.
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

# Set Flask routes in root to getting image file.
@app.route("/", methods=['GET'])
def return_meme():
    img_url = get_img_url()
    res = requests.get(img_url, stream=True)

    # Set MIME type as scraped image MIME. (jpeg, png, gif ...)
    content_type = res.raw.headers["Content-Type"]

    res.raw.decode_content = True
    img = Image.open(res.raw)
    return serve_pil_image(img, content_type)
