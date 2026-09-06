import random
import os
import asyncpraw
import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
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
cache_hot = TTLCache(maxsize=50, ttl=7200)
cache_top = TTLCache(maxsize=50, ttl=7200)
cache_rising = TTLCache(maxsize=50, ttl=7200)

@app.on_event("startup")
async def startup_event():
    app.state.session = aiohttp.ClientSession()
    app.state.cache_buffers = {
        "hot": [],
        "top": [],
        "rising": []
    }
    # 미리 받아 처리해 둔 바이트. 요청은 여기서 하나 고르기만 한다.
    app.state.ready = []
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
            "hot": (cache_hot, lambda sub, limit: sub.hot(limit=100)),
            "top": (cache_top, lambda sub, limit: sub.top(limit=100)),
            "rising": (cache_rising, lambda sub, limit: sub.rising(limit=100))
        }.items():
            new_cache = []
            fetched_urls = []

            # 클라이언트를 만들면 닫는다. 예전에는 카테고리마다 새로 만들고 한 번도
            # 닫지 않아 2시간마다 aiohttp 세션이 3개씩 샜다.
            reddit = get_reddit_client()
            try:
                subreddit = await reddit.subreddit("programmerhumor")

                # 최대 100개의 URL을 가져옴
                async for submission in category(subreddit, limit=100):
                    if not submission.is_self and (submission.url.endswith('.jpg') or submission.url.endswith('.png') or submission.url.endswith('.gif')):
                        if submission.url not in fetched_urls:
                            fetched_urls.append(submission.url)
                            # URL 유효성 검증 후 캐시에 추가
                            if await verify_image_url(submission.url):
                                new_cache.append(submission.url)
                            if len(new_cache) >= 50:
                                break
            finally:
                await reddit.close()
            
            if len(new_cache) > 0:
                print(f"{name} 캐시가 {len(new_cache)}개의 유효한 URL로 갱신되었습니다.")
                app.state.cache_buffers[name] = new_cache  # 새 캐시 버퍼에 저장
            else:
                print(f"{name} 캐시 갱신 실패: 유효한 URL을 찾지 못했습니다.")

        await prewarm()
        await asyncio.sleep(7200)  # 2시간 대기


async def prewarm(count=60):
    """URL 목록이 아니라 내보낼 바이트를 미리 만들어 둔다.

    예전에는 요청마다 Reddit 에서 이미지를 받아 PIL 로 처리했다. 왕복 바닥값이
    0.4초인데 응답 중앙값이 1.7초였던 게 그 때문이다. 갱신 때 한 번 해두면
    요청은 메모리에서 고르기만 하면 된다.
    """
    urls = []
    for name in ("hot", "top", "rising"):
        urls.extend(app.state.cache_buffers.get(name, []))
    if not urls:
        return

    ready = []
    for url in random.sample(urls, min(count, len(urls))):
        try:
            raw, image, content_type = await get_image_from_url(url)
            picked = prepare_bytes(raw, image, content_type)
            if picked:
                ready.append(picked)
        except Exception:
            continue  # ponytail: 한 장 실패는 넘긴다. 60장 중 몇 장 빠져도 상관없다

    if ready:
        app.state.ready = ready
        print(f"준비된 밈 {len(ready)}장 (합계 {sum(len(b) for b, _ in ready) // 1024}KB)")

# 캐시에서 무작위로 URL 가져오기
async def get_random_img_url():
    categories = {
        "hot": cache_hot,
        "top": cache_top,
        "rising": cache_rising
    }
    
    choice = random.choice(list(categories.keys()))
    cache = categories[choice]

    # 캐시가 비어있지 않은지 확인하고 스테이트 캐시를 가져오는 로직 개선
    if "image_urls" not in cache or len(cache["image_urls"]) == 0:
        print(f"{choice} 캐시가 비어있습니다. 스테이트 캐시를 가져옵니다.")
        if len(app.state.cache_buffers[choice]) > 0:
            cache["image_urls"] = app.state.cache_buffers[choice]
        else:
            raise HTTPException(status_code=500, detail=f"{choice} 캐시에 유효한 이미지 URL이 없습니다. 나중에 다시 시도해주세요.")

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
            return content, image, content_type
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="이미지를 가져오는 중 타임아웃 발생")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지를 가져오는 중 오류 발생: {str(e)}")

# 이 아래 크기면 아무것도 하지 않고 원본을 그대로 낸다.
# 디코딩·재인코딩이 응답 시간의 대부분이라, 안 하는 게 제일 빠르다.
PASS_THROUGH_BYTES = 300 * 1024
# 움짤 상한. 넘으면 축소하지 않고 다른 밈을 고른다 (이유는 prepare_bytes 주석 참고).
GIF_MAX_BYTES = 2 * 1024 * 1024
PICK_ATTEMPTS = 3


def prepare_bytes(raw, image, content_type):
    """내보낼 바이트를 정한다. None 이면 이 밈은 건너뛰고 다른 걸 고른다."""
    if getattr(image, "is_animated", False):
        # 움짤은 PIL 로 다시 인코딩하지 않는다. 실측에서 480x360 300KB 짜리가
        # 400x300 으로 줄였는데 2.6MB 가 됐다 — 원본이 갖고 있던 프레임 간 델타
        # 최적화가 재인코딩에서 통째로 날아가기 때문이다. 프레임을 유지하면서
        # 더 작게 만드는 건 gifsicle 급 도구가 필요한데, 밈 한 장 보여주자고
        # 들일 비용이 아니다. 그래서 크기로만 거르고 무거우면 다른 걸 고른다.
        return (raw, content_type) if len(raw) <= GIF_MAX_BYTES else None

    if len(raw) <= PASS_THROUGH_BYTES:
        return raw, content_type

    return compress_image(image, content_type).getvalue(), content_type


# 동적 압축 처리 함수
def compress_image(image, content_type):
    img_io = BytesIO()
    max_size = 1 * 1024 * 1024  # 1MB
    max_resolution = (400, 400)  # 최대 해상도 (너비, 높이)
    quality = 85

    # 줄일 거면 먼저 줄이고, 저장은 한 번만 한다.
    # 예전에는 같은 BytesIO 에 두 번 써서 원본 뒤에 썸네일이 이어 붙었다 —
    # tell() 이 원본+썸네일 합계를 내고, 1MB 아래면 그 버퍼가 그대로 나가서
    # 브라우저가 앞의 원본을 그렸다. 즉 축소가 무효였다.
    fmt = image.format
    if fmt != "GIF" and (image.size[0] > max_resolution[0] or image.size[1] > max_resolution[1]):
        # ponytail: GIF 는 건드리지 않는다. thumbnail() 이 첫 프레임만 남겨 움짤이 죽는다.
        print(f"이미지 해상도가 너무 큽니다. {image.size} -> {max_resolution}으로 줄입니다.")
        image.thumbnail(max_resolution, Image.LANCZOS)

    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=fmt)
    image_size = img_byte_arr.tell()

    # 이미지가 2MB를 초과하면 품질 조정
    if image_size > max_size:
        print(f"원본 이미지 크기가 {image_size / (1024 * 1024):.2f} MB로 너무 큽니다. 압축을 진행합니다...")

        # 품질을 낮추고 이미지 크기를 조정
        while image_size > max_size and quality > 10:
            img_io = BytesIO()
            if content_type == 'image/jpeg':
                image.save(img_io, format='JPEG', quality=quality)  # 품질 조정
            elif content_type == 'image/png':
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

# 키핑얼라이브용. 인스턴스만 깨우면 되므로 이미지를 받지 않는다.
# "/" 를 5분마다 찌르면 하루 288번 Reddit 에서 이미지를 내려받고 PIL 로 처리하게 된다.
@app.get("/health")
async def health():
    buf = getattr(app.state, "cache_buffers", {})
    return {"ok": True, "urls": {k: len(v) for k, v in buf.items()},
            "ready": len(getattr(app.state, "ready", []))}


# FastAPI 엔드포인트
@app.get("/")
async def return_meme():
    try:
        pool = getattr(app.state, "ready", [])
        if pool:
            data, out_type = random.choice(pool)
            return Response(content=data, media_type=out_type,
                            headers={"Cache-Control": "max-age=0"})

        # 아직 안 채워졌으면(부팅 직후) 예전 경로로 떨어진다.
        picked = None
        for _ in range(PICK_ATTEMPTS):
            img_url = await get_random_img_url()
            raw, image, content_type = await get_image_from_url(img_url)
            picked = prepare_bytes(raw, image, content_type)
            if picked:
                break
        if not picked:
            # 세 번 다 무거운 움짤이면 마지막 것을 그냥 낸다.
            # 느린 게 아무것도 안 보이는 것보다 낫다.
            picked = (raw, content_type)

        data, out_type = picked
        # Cache-Control: max-age=0 은 반드시 유지한다.
        # 새로고침할 때마다 밈이 바뀌는 게 이 헤더 덕이다.
        return Response(content=data, media_type=out_type,
                        headers={"Cache-Control": "max-age=0"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
