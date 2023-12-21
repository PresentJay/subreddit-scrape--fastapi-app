import random
import json
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

# set subreddit name
subredditName = "programmerhumor"

# set scraping candidate amount in subreddit once
fetchingAmount = 99

# get randomly picked one image url in candidate amount.
def getImgURL():
    # if you got error or not image, bot will rescrape target subreddit ${duration} times.
    duration = 5
    
    url = f"https://www.reddit.com/r/{subredditName}.json?limit={fetchingAmount}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Upgrade-Insecure-Requests': '1',
        'Dnt': '1',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': 'macOS',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }
    req = requests.get(url=url, headers=headers)
    if req.status_code == 200:
        try:
            json = req.json()
        except json.decoder.JSONDecodeError as e:
            print(f"JSON decoding error: {e}")
    else:
        print(f"Error: {req.status_code}")

    print(req.content)
    
    while duration >= 1:
        if "error" in json.keys():
            # for avoiding server ban raised by same repetition time, it will randomed in real value of [0-1].
            duration -= 1
            sleep(random.random())
            continue
        imgURLlist = json["data"]["children"]
        selected = random.choice(imgURLlist)
        if selected["data"]["post_hint"] == "image":
            return selected["data"]["url"]

# set given image streams to byte, downsizing, and return to file.
# TODO: some images still raising an error to show in github readme. I guess this is because of size or something.
def serve_pil_image(pil_img, contentType):
    img_io = BytesIO()
    pil_img.save(img_io, contentType.split('/').pop(), quality=70)
    img_io.seek(0)
    return send_file(img_io, mimetype=contentType)

@app.after_request
def set_response_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# set flask routes in root to getting image file.
@app.route("/", methods=['GET'])
def return_meme():
    img_url = getImgURL()
    res = requests.get(img_url, stream=True)

    # set MIME type as scraped image MIME. (jpeg, png, gif ...)
    contentType=res.raw.headers["Content-Type"]

    res.raw.decode_content = True
    img = Image.open(res.raw)
    return serve_pil_image(img, contentType)
