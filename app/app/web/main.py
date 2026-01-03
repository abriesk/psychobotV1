# app/web/main.py - FastAPI application entry point
"""
FastAPI web interface for PsychoBot.
Serves both client booking interface and admin management UI.
Authentication handled by Nginx Proxy Manager for /admin routes.
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os

from app.web.routers import client, admin

# Initialize FastAPI app
app = FastAPI(
    title="PsychoBot Web Interface",
    description="Web interface for psychotherapy booking bot",
    version="1.0"
)

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory="app/web/templates")

# Include routers
app.include_router(client.router, tags=["Client"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

# Root redirect
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect to client booking page"""
    return templates.TemplateResponse("client/index.html", {"request": request})

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check for monitoring"""
    return {"status": "healthy", "service": "psychobot-web"}

# Startup event
@app.on_event("startup")
async def startup_event():
    print("✅ FastAPI web server started")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    print("⏹️  FastAPI web server stopped")
