import random
import os
import aiohttp
import asyncio
import asyncpraw
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image
from io import BytesIO
from cachetools import TTLCache

app = FastAPI()

# Get Reddit API credentials from environment variables
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")

if not all([client_id, client_secret, username, password]):
    raise ValueError("Please set all required environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")

# Authenticate with asyncpraw
reddit = asyncpraw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    username=username,
    password=password,
    user_agent="Async Reddit Image Scraper"
)

# Caching for image URLs to reduce redundant requests
cache = TTLCache(maxsize=100, ttl=300)  # Cache with 100 items, TTL 300 seconds

async def fetch_posts(subreddit, sort_type, limit=50):
    """
    Fetch posts from a subreddit with a given sorting type.
    """
    posts = []
    if sort_type == 'hot':
        async for post in subreddit.hot(limit=limit):
            posts.append(post)
    elif sort_type == 'top':
        async for post in subreddit.top(limit=limit):
            posts.append(post)
    elif sort_type == 'rising':
        async for post in subreddit.rising(limit=limit):
            posts.append(post)
    return posts


async def get_img_urls():
    """
    Get image URLs from the 'programmerhumor' subreddit.
    """
    subreddit = await reddit.subreddit("programmerhumor")
    
    # Fetch posts concurrently
    hot_posts, top_posts, rising_posts = await asyncio.gather(
        fetch_posts(subreddit, 'hot'),
        fetch_posts(subreddit, 'top'),
        fetch_posts(subreddit, 'rising')
    )
    
    # Combine and filter image posts
    posts = hot_posts + top_posts + rising_posts
    image_posts = [post.url for post in posts if not post.is_self and (post.url.endswith('.jpg') or post.url.endswith('.png'))]
    return image_posts

async def get_image_from_url(url):
    """
    Fetch image from a given URL.
    """
    timeout = aiohttp.ClientTimeout(total=60)  # Set timeout to 60 seconds
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Error fetching image")
            content_type = response.headers["Content-Type"]
            content = await response.read()
            image = Image.open(BytesIO(content))
            return image, content_type

def serve_pil_image(image, content_type):
    """
    Serve a PIL image as an HTTP response.
    """
    img_io = BytesIO()
    image.save(img_io, format=content_type.split('/')[1].upper())
    img_io.seek(0)
    return StreamingResponse(img_io, media_type=content_type)

@app.get("/", response_class=StreamingResponse)
async def return_meme():
    """
    Return a random meme image from the 'programmerhumor' subreddit.
    """
    if "image_urls" not in cache:
        cache["image_urls"] = await get_img_urls()
    
    img_url = random.choice(cache["image_urls"])
    
    try:
        image, content_type = await get_image_from_url(img_url)
        return serve_pil_image(image, content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
