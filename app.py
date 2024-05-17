import random
import os
import praw
import requests
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

# Authenticate with praw
reddit = praw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    username=username,
    password=password,
    user_agent="Reddit Image Scraper"
)

# Get randomly picked one image URL in candidate amount
def get_img_url():
    subreddit = reddit.subreddit("programmerhumor")
    posts = subreddit.hot(limit=100)
    image_posts = [post.url for post in posts if post.post_hint == "image"]
    return random.choice(image_posts)

# Serve PIL image
def serve_pil_image(pil_img, content_type):
    img_io = BytesIO()
    pil_img.save(img_io, format="JPEG")
    img_io.seek(0)
    return send_file(img_io, mimetype=content_type)

@app.route("/", methods=["GET"])
def return_meme():
    img_url = get_img_url()
    response = requests.get(img_url)
    response.raise_for_status()
    content_type = response.headers["Content-Type"]
    image = Image.open(BytesIO(response.content))
    return serve_pil_image(image, content_type)

if __name__ == "__main__":
    app.run()
