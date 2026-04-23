# Security Considerations

This document outlines security considerations, best practices, and recommendations for securing Video Analyzer Web deployments.

## Current Security Status

### Strengths
- **File validation** - Extension whitelist, size limits, path traversal prevention
- **Input sanitization** - Filename sanitization, path verification
- **Error handling** - Consistent error responses without information leakage
- **Docker isolation** - Containerized deployment option

### Known Vulnerabilities
- **No authentication** - All endpoints publicly accessible
- **Permissive CORS** - `cors_allowed_origins="*"` allows any origin
- **Monolithic architecture** - `app.py` violates SRP, increasing attack surface
- **File upload risks** - Limited validation of video file contents
- **API key exposure** - OpenRouter/OpenWebUI keys in config files

## Security Recommendations

### 1. Authentication & Authorization

**Critical Priority:** Add authentication to prevent unauthorized access.

#### Recommended Implementation:
```python
# Basic API Key authentication
API_KEYS = {"client-1": "secret-key-123", "client-2": "secret-key-456"}

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if api_key not in API_KEYS.values():
            return api_error("Unauthorized", 401)
        return f(*args, **kwargs)
    return decorated

# Apply to routes
@app.route("/api/videos/upload")
@require_auth
def upload_video():
    # ...
```

#### OAuth 2.0 Alternative:
- Implement OAuth 2.0 with JWT tokens
- Use existing identity provider (Keycloak, Auth0, etc.)
- Add role-based access control (RBAC)

### 2. CORS Configuration

**High Priority:** Restrict CORS to trusted origins.

```python
# Current (insecure)
socketio = SocketIO(cors_allowed_origins="*")

# Recommended
ALLOWED_ORIGINS = [
    "http://localhost:10000",
    "http://192.168.1.100:10000",
    "https://yourdomain.com"
]

socketio = SocketIO(cors_allowed_origins=ALLOWED_ORIGINS)
```

### 3. Input Validation

#### File Uploads
```python
# Current validation (strengths)
- Extension whitelist: ['.mp4', '.avi', '.mov', '.mkv', '.webm']
- Size limit: 1GB
- Filename sanitization
- Path traversal prevention

# Additional recommendations:
- Content-type verification
- Magic number validation
- Virus scanning integration
- Temporary quarantine for suspicious files
```

#### API Inputs
```python
# Add schema validation
from pydantic import BaseModel, ValidationError

class VideoUploadSchema(BaseModel):
    filename: str
    fps: float = Field(gt=0, le=10)
    whisper_model: str = Field(pattern="^(base|large|tiny)$")
    
# Validate before processing
try:
    data = VideoUploadSchema(**request.json)
except ValidationError as e:
    return api_error(f"Invalid input: {e}", 400)
```

### 4. Secure Configuration

#### Environment Variables
```bash
# Never commit secrets to version control
# Use .env file (add to .gitignore)

# .env file
OPENROUTER_API_KEY=sk-or-...
OPENWEBUI_API_KEY=sk-...
SECRET_KEY=change-this-in-production
ALLOWED_ORIGINS=http://localhost:10000
```

#### Configuration Loading
```python
import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(24))
```

### 5. File System Security

#### Path Traversal Prevention
```python
# Current implementation (src/utils/security.py)
def verify_path(user_path, base_directory):
    """Prevent directory traversal attacks."""
    user_path = os.path.normpath(user_path)
    if not user_path.startswith(base_directory):
        raise SecurityError("Path traversal attempt detected")
    return True
```

#### File Permissions
```bash
# Recommended permissions
chmod 755 uploads/      # Read/write for owner, read for others
chmod 600 config/*.json # Read/write for owner only
chmod 700 jobs/         # Owner only (contains sensitive data)
```

### 6. Network Security

#### Firewall Configuration
```bash
# Allow only necessary ports
sudo ufw allow 10000/tcp  # Video Analyzer Web
sudo ufw allow 11434/tcp  # Ollama (if external)
sudo ufw deny from any to any
```

#### HTTPS Enforcement
```python
# For production deployments
# Use reverse proxy (nginx, Traefik) with HTTPS

# Flask-SocketIO with SSL
socketio.run(app, 
             host='0.0.0.0', 
             port=10000, 
             certfile='cert.pem',
             keyfile='key.pem')
```

### 7. Docker Security

#### Non-Root User
```dockerfile
# Dockerfile improvement
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# Create non-root user
RUN useradd -m -u 1000 appuser

# Switch to non-root user
USER appuser

# Copy files with correct ownership
COPY --chown=appuser:appuser . /app
```

#### Resource Limits
```yaml
# docker-compose.yml improvements
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '1'
          memory: 2G
```

#### Volume Security
```yaml
# Use read-only volumes where possible
volumes:
  - ./config:/app/config:ro  # Configuration read-only
  - ./uploads:/app/uploads:rw
```

### 8. API Security

#### Rate Limiting
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    default_limits=["100 per minute", "10 per second"]
)

@app.route("/api/videos/upload")
@limiter.limit("5 per minute")  # Upload rate limit
def upload_video():
    # ...
```

#### Request Validation
```python
# Validate all incoming requests
def validate_request():
    # Check content type
    if request.method in ["POST", "PUT"]:
        if not request.is_json:
            return api_error("Content-Type must be application/json", 415)
    
    # Check content length
    if request.content_length > 10 * 1024 * 1024:  # 10MB
        return api_error("Request too large", 413)
```

### 9. Logging & Monitoring

#### Security Logging
```python
import logging
from logging.handlers import RotatingFileHandler

security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)

handler = RotatingFileHandler(
    "security.log", 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
security_logger.addHandler(handler)

# Log security events
def log_security_event(event_type, details, ip_address=None):
    security_logger.warning({
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        "details": details,
        "ip": ip_address or request.remote_addr,
        "user_agent": request.user_agent.string
    })
```

#### Suspicious Activity Detection
- Multiple failed uploads from same IP
- Rapid API calls
- Unusual file patterns
- Path traversal attempts

### 10. Dependencies & Supply Chain

#### Regular Updates
```bash
# Update dependencies regularly
pip list --outdated
pip install -U -r requirements.txt

# Check for security vulnerabilities
pip-audit
bandit -r .
```

#### Dependency Pinning
```txt
# requirements.txt with exact versions
Flask==2.3.3
flask-socketio==5.3.6
eventlet==0.33.3
faster-whisper==0.10.0
```

### 11. Data Protection

#### Sensitive Data Handling
```python
# Never log sensitive data
# Bad:
logger.info(f"Processing with API key: {api_key}")

# Good:
logger.info("Processing with OpenRouter API")
```

#### Data Retention
```python
# Automatic cleanup of old data
def cleanup_old_jobs(max_age_days=30):
    """Delete job data older than max_age_days."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    
    for job_dir in Path(JOBS_DIR).iterdir():
        if job_time < cutoff:
            shutil.rmtree(job_dir)
```

### 12. Emergency Response

#### Incident Response Plan
1. **Detection** - Monitor logs for anomalies
2. **Containment** - Block suspicious IPs, disable affected endpoints
3. **Eradication** - Remove malicious files, update credentials
4. **Recovery** - Restore from backups, verify integrity
5. **Post-mortem** - Document incident, improve defenses

#### Backup Strategy
```bash
# Regular backups of important data
# config/default_config.json
# Important job results
# Custom configurations

# Example backup script
tar -czf backup-$(date +%Y%m%d).tar.gz \
  config/ \
  jobs/*/results.json \
  --exclude="jobs/*/frames" \
  --exclude="uploads/*/frames"
```

## Deployment Scenarios

### Development Environment
- Localhost only
- Minimal security requirements
- Debug mode enabled
- All origins allowed

### Internal Network
- Firewall restricts access to internal IPs
- Basic authentication (API keys)
- Limited CORS
- HTTPS recommended

### Public Internet (High Risk)
- **Mandatory**: HTTPS with valid certificate
- **Mandatory**: Authentication system
- **Mandatory**: Rate limiting
- **Recommended**: Web Application Firewall (WAF)
- **Recommended**: Intrusion Detection System (IDS)

## Security Testing

### Manual Testing
1. **File upload bypass** - Try alternative extensions, magic numbers
2. **Path traversal** - Attempt `../../../etc/passwd`
3. **SQL injection** - Test API parameters (though no SQL used)
4. **XSS** - Test file names, API parameters for script injection
5. **CSRF** - Test SocketIO endpoints

### Automated Testing
```bash
# Static analysis
bandit -r .  # Security linter
safety check  # Dependency vulnerability scanner

# Dynamic analysis
# Use OWASP ZAP or Burp Suite
```

### Penetration Testing Checklist
- [ ] Authentication bypass attempts
- [ ] File upload exploitation
- [ ] API endpoint enumeration
- [ ] Information disclosure
- [ ] Denial of service testing
- [ ] Business logic flaws

## Compliance Considerations

### GDPR (If applicable)
- Data minimization - Only collect necessary video files
- Right to erasure - Implement video deletion API
- Data portability - Export functionality for user data
- Privacy by design - Log minimal personal data

### HIPAA (If processing medical videos)
- **Not currently compliant**
- Would require: encryption at rest, audit logging, BAAs
- Consider specialized deployment for medical use

### General Best Practices
- Principle of least privilege
- Defense in depth
- Regular security updates
- Security awareness training for users

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do not disclose publicly**
2. **Email**: security@yourdomain.com
3. **Include**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

4. **Expected response time**: 48 hours for acknowledgment
5. **Fix timeline**: Critical issues within 7 days

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Checklist](https://flask.palletsprojects.com/en/stable/security/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [NVIDIA Container Toolkit Security](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/security.html)

**Disclaimer**: This document provides security recommendations. Actual security implementation should be tailored to your specific deployment scenario and risk assessment. Consider consulting with security professionals for production deployments.