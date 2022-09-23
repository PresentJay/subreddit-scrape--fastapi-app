import random
import requests
from flask import Flask, send_file
from PIL import Image
from io import BytesIO

app = Flask(__name__)
subredditName = "ProgrammerHumor"
fetchingAmount = 99

def getImgURL():
    url = f"https://www.reddit.com/r/{subredditName}.json?limit={fetchingAmount}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:20.0) Gecko/20100101 Firefox/20.0'}
    req = requests.get(url=url, headers=headers)
    json = req.json()
    while True:
        if "error" in json.keys():
            print(json)
            exit(1)
        imgURLlist = json["data"]["children"]
        selected = random.choice(imgURLlist)
        if selected["data"]["post_hint"] == "image":
            return selected["data"]["url"]

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

@app.route("/", methods=['GET'])
def return_meme():
    img_url = getImgURL()
    res = requests.get(img_url, stream=True)
    contentType=res.raw.headers["Content-Type"]

    res.raw.decode_content = True
    img = Image.open(res.raw)
    return serve_pil_image(img, contentType)
