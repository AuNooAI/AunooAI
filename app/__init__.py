from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes.prompt_routes import router as prompt_router
from .routes.web_routes import router as web_router

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(web_router)  # Web routes at root level
app.include_router(prompt_router)  # API routes with /api prefix

# Add template context processor
@app.middleware("http")
async def add_template_context(request, call_next):
    response = await call_next(request)
    return response
