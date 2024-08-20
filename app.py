import random
import os
import asyncpraw
import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image, ImageSequence, ImageOps
from io import BytesIO
from cachetools import TTLCache

app = FastAPI()

# Reddit API 자격 증명 불러오기
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")

if not all([client_id, client_secret, username, password]):
    raise ValueError("필수 환경 변수를 설정해주세요: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")

# 캐싱을 통한 이미지 URL 요청 감소 (2시간 TTL)
cache_hot = TTLCache(maxsize=100, ttl=7200)
cache_top = TTLCache(maxsize=100, ttl=7200)
cache_rising = TTLCache(maxsize=100, ttl=7200)

@app.on_event("startup")
async def startup_event():
    app.state.session = aiohttp.ClientSession()
    app.state.cache_buffers = {
        "hot": [],
        "top": [],
        "rising": []
    }
    asyncio.create_task(refresh_cache_periodically())  # 주기적 캐시 갱신 작업

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.session.close()

# Reddit 클라이언트 초기화
def get_reddit_client():
    return asyncpraw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent="Async Reddit Image Scraper"
    )

# URL 유효성 검증을 위한 HEAD 요청
async def verify_image_url(url):
    session = app.state.session
    try:
        async with session.head(url) as response:
            if response.status != 200 or "image" not in response.headers["Content-Type"]:
                return False
            return True
    except Exception:
        return False

# 주기적으로 캐시를 갱신하는 함수
async def refresh_cache_periodically():
    while True:
        for name, (cache, category) in {
            "hot": (cache_hot, lambda sub, limit: sub.hot(limit=70)),
            "top": (cache_top, lambda sub, limit: sub.top(limit=70)),
            "rising": (cache_rising, lambda sub, limit: sub.rising(limit=70))
        }.items():
            new_cache = []
            fetched_urls = []

            reddit = get_reddit_client()
            subreddit = await reddit.subreddit("programmerhumor")
            
            # 최대 70개의 URL을 가져옴
            async for submission in category(subreddit, limit=70):
                if not submission.is_self and (submission.url.endswith('.jpg') or submission.url.endswith('.png') or submission.url.endswith('.gif')):
                    if submission.url not in fetched_urls:
                        fetched_urls.append(submission.url)
                        # URL 유효성 검증 후 캐시에 추가
                        if await verify_image_url(submission.url):
                            new_cache.append(submission.url)
                        if len(new_cache) >= 50:
                            break
            
            print(f"{name} 캐시가 {len(new_cache)}개의 유효한 URL로 갱신되었습니다.")
            app.state.cache_buffers[name] = new_cache  # 새 캐시 버퍼에 저장
        else:
            await asyncio.sleep(7200)  # 2시간 대기

# 캐시에서 무작위로 URL 가져오기
async def get_random_img_url():
    categories = {
        "hot": cache_hot,
        "top": cache_top,
        "rising": cache_rising
    }
    
    choice = random.choice(list(categories.keys()))
    cache = categories[choice]
    
    if "image_urls" not in cache:
        print(f"{choice} 캐시가 비어있습니다. 스테이트 캐시를 가져옵니다.")
        cache["image_urls"] = app.state.cache_buffers[choice]  # 새 캐시로 교체
    
    image_urls = cache["image_urls"]
    
    if len(image_urls) == 0:
        raise HTTPException(status_code=500, detail=f"{choice} 캐시가 비어 있습니다. 나중에 다시 시도해주세요.")
    
    return random.choice(image_urls)

# 비동기 이미지 가져오기
async def get_image_from_url(url):
    session = app.state.session
    try:
        async with session.get(url) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="이미지를 가져오는 중 오류 발생")
            content_type = response.headers["Content-Type"]
            content = await response.read()
            image = Image.open(BytesIO(content))
            return image, content_type
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="이미지를 가져오는 중 타임아웃 발생")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지를 가져오는 중 오류 발생: {str(e)}")

# 동적 압축 처리 함수
def compress_image(image, content_type):
    img_io = BytesIO()
    max_size = 2 * 1024 * 1024  # 2MB
    quality = 85

    # 원본 이미지 크기 확인
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=image.format)
    image_size = img_byte_arr.tell()

    # 이미지가 2MB를 초과하면 크기를 조절
    if image_size > max_size:
        print(f"원본 이미지 크기가 {image_size / (1024 * 1024):.2f} MB로 너무 큽니다. 압축을 진행합니다...")

        # 품질을 낮추고 이미지 크기를 조정
        while image_size > max_size and quality > 10:
            img_io = BytesIO()
            if content_type == 'image/jpeg':
                image.save(img_io, format='JPEG', quality=quality)  # 품질 조정
            elif content_type == 'image/png':
                image = ImageOps.exif_transpose(image)
                image.save(img_io, format='PNG', optimize=True)
            elif content_type == 'image/gif':
                frames = [frame.copy() for frame in ImageSequence.Iterator(image)]
                frames[0].save(img_io, format='GIF', save_all=True, append_images=frames[1:], optimize=True)
            else:
                raise HTTPException(status_code=415, detail="지원되지 않는 미디어 유형입니다.")
            
            img_byte_arr = img_io
            image_size = img_byte_arr.tell()
            quality -= 10  # 품질을 단계적으로 낮춤

        print(f"최종 이미지 크기는 {image_size / (1024 * 1024):.2f} MB입니다.")

    else:
        print(f"이미지 크기는 {image_size / (1024 * 1024):.2f} MB로 적절합니다. 압축 불필요.")
        img_io = img_byte_arr

    img_io.seek(0)
    return img_io

# 이미지 스트리밍 함수
def stream_compressed_image(image_io, content_type):
    return StreamingResponse(image_io, media_type=content_type)

# FastAPI 엔드포인트
@app.get("/", response_class=StreamingResponse)
async def return_meme():
    img_url = await get_random_img_url()

    headers = {
        "Cache-Control": "no-cache"  # 캐시 제어 헤더 추가
    }
    
    try:
        image, content_type = await get_image_from_url(img_url)
        compressed_image_io = compress_image(image, content_type)
        return StreamingResponse(content=compressed_image_io, media_type=content_type, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
