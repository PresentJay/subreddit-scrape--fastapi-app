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

# 이미지 게시물을 식별하여 이미지 URL 가져오기
def get_img_url():
    subreddit = reddit.subreddit("programmerhumor")
    endpoints = [subreddit.hot, subreddit.top, subreddit.rising]
    posts = []
    
    for endpoint in endpoints:
        posts.extend(endpoint(limit=50))
    
    image_posts = [post.url for post in posts if not post.is_self and (post.url.endswith('.jpg') or post.url.endswith('.png'))]
    return random.choice(image_posts) if image_posts else None
    
# 이미지 가져오기
def get_image_from_url(url):
    response = requests.get(url)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    return image, response.headers["Content-Type"]

# Serve PIL image
def serve_pil_image(image, content_type):
    img_io = BytesIO()
    image.save(img_io, format=content_type.split('/')[1].upper())
    img_io.seek(0)
    return send_file(img_io, mimetype=content_type)

@app.route("/", methods=["GET"])
def return_meme():
    img_url = get_img_url()
    if img_url:
        image, content_type = get_image_from_url(img_url)
        return serve_pil_image(image, content_type)
    else:
        return "No image found"

if __name__ == "__main__":
    app.run()
