# Fastapi
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler

# Database
from database import engine, Base

# Cross Origin Resource Sharing (front and backend connection)
from fastapi.middleware.cors import CORSMiddleware

from starlette.exceptions import HTTPException as StarletteHTTPException

from routers import admins, cart, orders, products, users

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: table creation in database (create_all is sync, run_sync runs it on the async connection)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

# CORS configuration
origins = [
    "http://localhost:5173",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(cart.router, prefix="/api/cart", tags=["cart"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(admins.router, prefix="/api/admin", tags=["admin"])


# Handle General HTTP Errors
@app.exception_handler(StarletteHTTPException)
async def handle_general_http_errors(request: Request, exception: StarletteHTTPException):
    return await http_exception_handler(request, exception) # {"detail": ...} with the exception's status code (and headers, e.g. WWW-Authenticate)

# Handle Validation Errors
@app.exception_handler(RequestValidationError)
async def handle_validation_errors(request: Request, exception: RequestValidationError):
    return await request_validation_exception_handler(request, exception) # 422 with {"detail": [errors]}
