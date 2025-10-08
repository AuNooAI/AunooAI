# Environment Setup Guide

## Virtual Environment Setup

### Linux/macOS
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Verify activation (should show .venv path)
which python
```

### Windows
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Verify activation (should show venv path)
where python
```

## Application Entry Points

### Development (Local Testing)
```bash
# After activating virtual environment
python app/main.py
```

**Features:**
- Hot reload enabled
- Debug logging
- Development-only middleware
- Accessible at http://localhost:8000

### Production (Internet-Facing Server)
```bash
# After activating virtual environment
python app/server_run.py
```

**Features:**
- SSL/TLS configuration
- Reverse proxy compatibility
- Production logging
- Health check endpoints
- Process management
- Optimized for Nginx/Apache reverse proxy

## Environment Variables

Create `.env` file in project root:

```env
# Required API Keys
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
NEWSAPI_KEY=your_newsapi_key_here
THENEWSAPI_KEY=your_thenewsapi_key_here
FIRECRAWL_API_KEY=your_firecrawl_key_here

# Optional API Keys
HUGGINGFACE_API_KEY=your_huggingface_key_here
GEMINI_API_KEY=your_gemini_key_here

# Application Settings
ENVIRONMENT=dev  # dev, staging, or production
SECRET_KEY=your_random_secret_key_here
DATABASE_DIR=app/data
```

## Complete Setup Process

### 1. Clone Repository
```bash
git clone <repository-url>
cd AunooAI
```

### 2. Setup Virtual Environment

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
# Copy example env file
cp .env.example .env
# Edit .env with your API keys
```

### 5. Run Database Migrations
```bash
python run_migration.py
```

### 6. Start Application

**Development:**
```bash
python app/main.py
```

**Production:**
```bash
python app/server_run.py
```

## Platform-Specific Notes

### Linux
- Virtual environment: `.venv`
- Activation: `source .venv/bin/activate`
- Python path: `which python`

### Windows
- Virtual environment: `venv`
- Activation: `venv\Scripts\activate`
- Python path: `where python`

### macOS
- Virtual environment: `.venv`
- Activation: `source .venv/bin/activate`
- Python path: `which python`

## Production Deployment

### With Reverse Proxy (Nginx)

**Nginx Configuration:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Start Application:**
```bash
# Use production entry point
python app/server_run.py
```

### With Docker

```bash
# Build image
docker-compose build

# Run development instance
docker-compose up -d aunooai-dev

# Run production instance
docker-compose --profile prod up -d
```

## Troubleshooting

### Virtual Environment Issues

**Linux/macOS - Permission Denied:**
```bash
chmod +x .venv/bin/activate
source .venv/bin/activate
```

**Windows - Execution Policy:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\activate
```

### Port Already in Use

**Development:**
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9  # Linux/macOS
netstat -ano | findstr :8000   # Windows
```

**Production:**
```bash
# Check if server_run.py is already running
ps aux | grep server_run.py    # Linux/macOS
tasklist | findstr python      # Windows
```

### Environment Variables Not Loading

```bash
# Verify .env file exists
ls -la .env                    # Linux/macOS
dir .env                       # Windows

# Check if variables are loaded
python -c "import os; print(os.getenv('OPENAI_API_KEY'))"
```

## Quick Commands Reference

| Action | Linux/macOS | Windows |
|--------|-------------|---------|
| Create venv | `python -m venv .venv` | `python -m venv venv` |
| Activate | `source .venv/bin/activate` | `venv\Scripts\activate` |
| Deactivate | `deactivate` | `deactivate` |
| Install deps | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Dev server | `python app/main.py` | `python app/main.py` |
| Prod server | `python app/server_run.py` | `python app/server_run.py` |
| Run tests | `pytest tests/ -v` | `pytest tests/ -v` |
| Check Python | `which python` | `where python` |

## Next Steps

1. **Verify Setup**: Run `python app/main.py` and visit http://localhost:8000
2. **Configure API Keys**: Add your API keys to `.env` file
3. **Run Migrations**: Execute `python run_migration.py`
4. **Start Development**: Use `python app/main.py` for local development
5. **Deploy Production**: Use `python app/server_run.py` for production
