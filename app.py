import random
import os
import asyncpraw
import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image
from io import BytesIO
from cachetools import TTLCache
from contextlib import asynccontextmanager

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = aiohttp.ClientSession()
    yield
    await app.state.session.close()

app.lifespan(lifespan)

# 이미지 게시물을 식별하여 이미지 URL 가져오기
async def get_img_urls():
    subreddit = await reddit.subreddit("programmerhumor")
    image_posts = []
    
    async for submission in subreddit.hot(limit=50):
        if not submission.is_self and (submission.url.endswith('.jpg') or submission.url.endswith('.png')):
            image_posts.append(submission.url)
            
    async for submission in subreddit.top(limit=50):
        if not submission.is_self and (submission.url.endswith('.jpg') or submission.url.endswith('.png')):
            image_posts.append(submission.url)
            
    async for submission in subreddit.rising(limit=50):
        if not submission.is_self and (submission.url.endswith('.jpg') or submission.url.endswith('.png')):
            image_posts.append(submission.url)
                
    return image_posts

# 비동기 이미지 가져오기
async def get_image_from_url(url):
    session = app.state.session
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Error fetching image")
            content_type = response.headers["Content-Type"]
            content = await response.read()
            image = Image.open(BytesIO(content))
            return image, content_type
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout while fetching image")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching image: {str(e)}")

# Serve PIL image
def serve_pil_image(image, content_type):
    img_io = BytesIO()
    image.save(img_io, format=content_type.split('/')[1].upper())
    img_io.seek(0)
    return StreamingResponse(img_io, media_type=content_type)

@app.get("/", response_class=StreamingResponse)
async def return_meme():
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
