import logging
import asyncio
import sys
from quart import Quart, request, Response, jsonify
import httpx
import hypercorn.asyncio
import hypercorn.config

# Linux/macOS에서만 uvloop 적용
if sys.platform != "win32":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

app = Quart(__name__)

# 글로벌 HTTP 클라이언트 (연결 재사용)
client = httpx.AsyncClient(http2=True, timeout=30.0)

async def proxy_request(base_url, path):
    url = f"{base_url}/{path}" if path else base_url
    method = request.method
    headers = {key: value for key, value in request.headers.items() if key.lower() not in ["host", "content-length"]}
    data = await request.data

    try:
        resp = await client.request(method, url, headers=headers, content=data, params=request.args)

        response = Response(resp.content, status=resp.status_code, mimetype=resp.headers.get('Content-Type', 'application/octet-stream'))
        for key, value in resp.headers.items():
            response.headers[key] = value
        return response
    except httpx.HTTPError as e:
        return jsonify({"error": "Failed to connect to the backend", "details": str(e)}), 502

# 서비스 A (포트 8188)로 요청을 프록시
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
async def proxy_a(path):
    return await proxy_request('http://127.0.0.1:8188', path)

# 서비스 B (포트 8189)로 요청을 프록시
@app.route('/infinite_image_browsing', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/infinite_image_browsing/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
async def proxy_b(path):
    return await proxy_request('http://127.0.0.1:8189/infinite_image_browsing', path)

# HTTP 클라이언트 시작 및 종료 처리
@app.before_serving
async def startup():
    global client
    client = httpx.AsyncClient(http2=True, timeout=60.0)

@app.after_serving
async def shutdown():
    await client.aclose()

# 로그 레벨 설정 (ERROR 이상만 출력)
logging.getLogger("hypercorn.access").setLevel(logging.ERROR)
logging.getLogger("hypercorn.error").setLevel(logging.ERROR)
logging.getLogger("quart.app").setLevel(logging.ERROR)

# Hypercorn 실행
if __name__ == '__main__':
    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:8800"]
    config.keep_alive_timeout = 120  # 타임아웃 증가
    asyncio.run(hypercorn.asyncio.serve(app, config))
