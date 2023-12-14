import random
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO
from time import sleep

app = Flask(__name__)

# set subreddit name
subredditName = "ProgrammerHumor"

# set scraping candidate amount in subreddit once
fetchingAmount = 99

# get randomly picked one image url in candidate amount.
def getImgURL():
    # if you got error or not image, bot will rescrape target subreddit ${duration} times.
    duration = 5
    
    url = f"https://www.reddit.com/r/{subredditName}.json?limit={fetchingAmount}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:20.0) Gecko/20100101 Firefox/20.0'}
    req = requests.get(url=url, headers=headers)
    json = req.json()
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
