import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import html
import json
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import init_db
from .api import auth_routes, customers, imports, profiles, admin

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app=FastAPI(title='企业客户智能 CRM',version='0.1.0',lifespan=lifespan,docs_url=None,redoc_url=None)

@app.middleware('http')
async def security_headers(request:Request,call_next):
    if request.url.path.startswith('/api/') and request.method not in ['GET','HEAD','OPTIONS']:
        if request.headers.get('x-crm-request')!='1':
            return JSONResponse({'detail':'缺少同源请求标记'},status_code=403)
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc!=request.headers.get('host'):
            return JSONResponse({'detail':'不允许跨站请求'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    if request.url.path.startswith('/static/'):
        response.headers['Cache-Control']='no-cache'
    return response

@app.exception_handler(RequestValidationError)
async def invalid_input(request,exc):
    return JSONResponse({'detail': [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]},status_code=422)

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return JSONResponse({'detail':'数据冲突，名称或记录可能重复，请刷新后重试'},status_code=409)

@app.exception_handler(OperationalError)
async def database_error(request,exc):
    logging.getLogger('crm').error('Database operation failed (%s)',type(exc).__name__)
    return JSONResponse({'detail':'数据库暂时忙碌或不可用，请重试；持续失败请联系管理员'},status_code=503)

for router in [auth_routes.router,customers.router,imports.router,profiles.router,admin.router]:
    app.include_router(router)
STATIC=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')

@app.get('/',include_in_schema=False)
def index():
    return FileResponse(STATIC/'index.html')

@app.get('/health',include_in_schema=False)
def health():
    return {'status':'ok'}


@app.get('/docs',include_in_schema=False,response_class=HTMLResponse)
def api_docs():
    schema=app.openapi()
    rows=[]
    for path,methods in schema['paths'].items():
        for method,operation in methods.items():
            rows.append('<tr><td>'+html.escape(method.upper())+'</td><td>'+html.escape(path)+'</td><td>'+html.escape(operation.get('summary',''))+'</td></tr>')
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CRM 接口文档</title><link rel="stylesheet" href="/static/css/style.css"></head><body><main class="content"><h1>企业客户 CRM 接口文档</h1><p class="hint">离线文档。写操作需登录 Cookie、X-CRM-Request: 1 和 X-CSRF-Token；首次改密前只允许认证操作。</p><p><a href="/">返回应用</a> · <a href="/openapi.json">OpenAPI JSON</a></p><section class="panel"><div class="table-wrap"><table><thead><tr><th>方法</th><th>路径</th><th>接口</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section><details><summary>完整请求 Schema</summary><pre class="evidence">'+html.escape(json.dumps(schema.get('components',{}),ensure_ascii=False,indent=2))+'</pre></details></main></body></html>'
