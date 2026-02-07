# Smart Work Sequencer - Backend

A Django REST API backend that automatically tracks and summarizes developer work by correlating GitHub activity and Jira activity.

## Features

- **OAuth Authentication**: Secure OAuth 2.0 integration with GitHub and Jira (Atlassian)
- **GitHub Integration**: Fetch commits, PRs, and extract Jira ticket references from commit messages
- **Jira Integration**: Track tickets, status changes, comments, and time worklogs
- **Smart Reporting**: AI-powered work summaries using OpenAI GPT-4
- **Hygiene Detection**: Identify missing ticket references, stalled tickets, and workflow issues
- **Automated Weekly Reports**: Celery-based automated report generation

## Tech Stack

- **Framework**: Django 5.x + Django REST Framework
- **Database**: PostgreSQL (GCP Cloud SQL compatible)
- **Task Queue**: Celery + Redis
- **AI**: OpenAI GPT-4 for smart summaries
- **Security**: Encrypted token storage using Fernet

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (for Celery)
- GitHub OAuth App credentials
- Jira/Atlassian OAuth 2.0 credentials
- OpenAI API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/smart-work-sequencer-backend.git
cd smart-work-sequencer-backend
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add the output to ENCRYPTION_KEY in .env
```

6. Run migrations:
```bash
python manage.py migrate
```

7. Create superuser (optional):
```bash
python manage.py createsuperuser
```

### Running the Server

Development:
```bash
python manage.py runserver
```

Production (with Gunicorn):
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Running Celery

Worker:
```bash
celery -A config worker -l info
```

Beat (for scheduled tasks):
```bash
celery -A config beat -l info
```

## API Endpoints

### Authentication
- `POST /api/auth/register/` - Register new user
- `POST /api/auth/login/` - Login and get JWT token
- `GET /api/auth/me/` - Get current user info
- `GET /api/auth/connections/` - Get OAuth connection status
- `GET /api/auth/github/` - Get GitHub OAuth URL
- `GET /api/auth/github/callback/` - GitHub OAuth callback
- `GET /api/auth/jira/` - Get Jira OAuth URL
- `GET /api/auth/jira/callback/` - Jira OAuth callback

### Integrations
- `GET /api/integrations/github/repositories/` - List GitHub repositories
- `POST /api/integrations/github/repositories/sync/` - Sync repositories from GitHub
- `POST /api/integrations/github/commits/sync/` - Sync commits for date range
- `GET /api/integrations/github/commits/` - List commits with filters
- `GET /api/integrations/jira/projects/` - List Jira projects
- `POST /api/integrations/jira/projects/sync/` - Sync projects from Jira
- `POST /api/integrations/jira/sync/` - Sync Jira data for date range
- `GET /api/integrations/jira/tickets/` - List tickets with filters

### Reports
- `POST /api/reports/generate/` - Generate report for date range
- `GET /api/reports/weekly/` - List weekly reports
- `POST /api/reports/weekly/create/` - Create weekly report
- `GET /api/reports/weekly/current/` - Get current week report
- `GET /api/reports/weekly/last/` - Get last week report
- `GET /api/reports/analytics/effort/` - Get effort vs output analysis
- `GET /api/reports/hygiene/` - List hygiene alerts
- `GET /api/reports/hygiene/summary/` - Get hygiene summary
- `POST /api/reports/hygiene/detect/` - Detect hygiene issues
- `POST /api/reports/hygiene/resolve/` - Resolve hygiene alerts

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Debug mode (True/False) |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL username |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port |
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `GITHUB_REDIRECT_URI` | GitHub OAuth redirect URI |
| `JIRA_CLIENT_ID` | Atlassian OAuth client ID |
| `JIRA_CLIENT_SECRET` | Atlassian OAuth client secret |
| `JIRA_REDIRECT_URI` | Jira OAuth redirect URI |
| `OPENAI_API_KEY` | OpenAI API key |
| `REDIS_URL` | Redis URL for Celery |
| `ENCRYPTION_KEY` | Fernet encryption key for tokens |
| `FRONTEND_URL` | Frontend URL for OAuth redirects |

## GCP Deployment

### Cloud Run

1. Build Docker image:
```bash
docker build -t gcr.io/PROJECT_ID/smart-work-sequencer-backend .
```

2. Push to Container Registry:
```bash
docker push gcr.io/PROJECT_ID/smart-work-sequencer-backend
```

3. Deploy to Cloud Run:
```bash
gcloud run deploy smart-work-sequencer-backend \
  --image gcr.io/PROJECT_ID/smart-work-sequencer-backend \
  --platform managed \
  --region us-central1 \
  --set-env-vars "DJANGO_SETTINGS_MODULE=config.settings"
```

### Cloud SQL

1. Create PostgreSQL instance in GCP Console
2. Update `DB_HOST` to use Cloud SQL connection string
3. Configure VPC connector for Cloud Run

## License

MIT
