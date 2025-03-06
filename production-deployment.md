# Production Deployment Guide

This guide outlines the best practices for deploying the MCP Server in production environments using containers (Docker or Podman).

## Production-Ready Configuration

### Recommended Setup

For a robust production deployment, we recommend:

1. Using a proper database backend (PostgreSQL/MySQL) instead of SQLite
2. Setting up a reverse proxy (Nginx/Traefik) with TLS
3. Implementing proper authentication
4. Setting up monitoring and logging
5. Configuring automatic restarts and health checks

## Container Orchestration

### Docker Compose for Production

The included `docker-compose.yml` file provides a good starting point for production:

```bash
# Start the production stack
docker-compose up -d

# Scale if needed (for the web service)
docker-compose up -d --scale mcp-server=2
```

### Using Podman in Production

For Red Hat environments, Podman provides a more secure alternative:

```bash
# Using podman-compose
podman-compose up -d

# Or manual pod creation
podman pod create --name mcp-pod -p 5000:5000
podman run -d --pod mcp-pod --name mcp-db postgres:13-alpine
podman run -d --pod mcp-pod --name mcp-server mcp-server
```

### Kubernetes/OpenShift Deployment

For larger scale deployments, use Kubernetes or OpenShift:

1. Create Kubernetes manifests in `k8s/` directory
2. Apply the configuration:

```bash
kubectl apply -f k8s/

# Or for OpenShift
oc apply -f k8s/
```

## Database Configuration

### Using PostgreSQL

Update your `.env` file to use PostgreSQL:

```
MEMORY_DB_URI=postgresql://mcp:mcppassword@db:5432/mcp
```

### Database Migrations

If you're upgrading or need to migrate data:

```bash
# Inside the container
flask db upgrade
```

## Web Server Configuration

### Using Gunicorn

For production, replace the development server with Gunicorn:

1. Update the Dockerfile:

```dockerfile
CMD ["gunicorn", "--workers=4", "--bind=0.0.0.0:5000", "app:app"]
```

2. Or override the command in docker-compose.yml:

```yaml
command: gunicorn --workers=4 --bind=0.0.0.0:5000 app:app
```

### Reverse Proxy with Nginx

Set up Nginx as a reverse proxy in front of the application:

```nginx
server {
    listen 80;
    server_name mcp.example.com;
    
    location / {
        proxy_pass http://mcp-server:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Hardening

### Environment Variables

Never commit sensitive environment variables. Use secrets management:

```bash
# For Docker Swarm
docker secret create mcp_env .env
docker service create --secret mcp_env mcp-server

# For Kubernetes
kubectl create secret generic mcp-secrets --from-env-file=.env
```

### Container Security

1. Run as non-root user:

```dockerfile
USER 1001
```

2. Use read-only file systems where possible:

```yaml
volumes:
  - ./data:/app/data:ro
```

3. Use security scanning:

```bash
# Scan the image
docker scan mcp-server

# Or with Podman
podman image scan mcp-server
```

## Monitoring and Logging

### Prometheus Metrics

Expose metrics for Prometheus monitoring:

```python
# Add to app.py
from prometheus_client import Counter, Histogram, start_http_server
```

### Centralized Logging

Configure logging to a central service:

```yaml
# docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

Or integrate with ELK/Graylog:

```yaml
logging:
  driver: "gelf"
  options:
    gelf-address: "udp://localhost:12201"
```

## High Availability Setup

### Load Balancing

Use a load balancer in front of multiple instances:

```yaml
# docker-compose.yml
services:
  mcp-server:
    deploy:
      replicas: 3
  
  lb:
    image: traefik:v2.4
    ports:
      - "80:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

### Health Checks and Auto-healing

Configure health checks for automatic recovery:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## Backup Strategy

### Database Backups

Regularly backup the database:

```bash
# For PostgreSQL
docker exec mcp-db pg_dump -U mcp mcp > backup.sql

# Restore if needed
cat backup.sql | docker exec -i mcp-db psql -U mcp mcp
```

### Volume Backups

Backup mounted volumes:

```bash
docker run --rm -v mcp_data:/source:ro -v $(pwd):/backup alpine tar -czvf /backup/mcp-data.tar.gz -C /source .
```

## Rolling Updates

### Zero-Downtime Deployment

Perform rolling updates without downtime:

```bash
# With Docker Compose
docker-compose up -d --no-deps --build mcp-server

# With Kubernetes
kubectl set image deployment/mcp-server mcp-server=mcp-server:new
```

## Testing Your Production Deployment

### Smoke Tests

Run basic smoke tests against the production instance:

```bash
# Test API endpoints
curl -f http://mcp.example.com/health
curl -f http://mcp.example.com/mcp/manifest
```

### Load Testing

Test performance under load:

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://mcp.example.com/health
```

## CI/CD Pipeline Integration

### Docker Hub / GitHub Actions

Example GitHub Actions workflow for automatic builds:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build and Push
        uses: docker/build-push-action@v2
        with:
          push: true
          tags: yourusername/mcp-server:latest
```

## Disaster Recovery

### Failover Strategy

Document your failover process:

1. Identify backup servers or cloud regions
2. Maintain recent backups
3. Test recovery procedures regularly
4. Document recovery time objectives (RTO)

### Recovery Procedure

Steps to recover from a disaster:

1. Deploy new infrastructure
2. Restore database from backup
3. Validate application functionality
4. Update DNS records if needed

## Conclusion

By following these production deployment best practices, you will have a robust, secure, and maintainable MCP Server deployment that can handle production workloads reliably.

Remember to regularly review logs, monitor performance, and update dependencies to maintain a healthy production environment.
