# Container Deployment Guide

This guide covers deploying the MCP Server using containers on both Docker and Podman, with specific instructions for Fedora and other Red Hat based systems.

## Docker vs Podman on Red Hat Systems

### Docker

Docker is a widely used container runtime that works across multiple platforms. If you already have Docker installed on your Fedora system, you can use it to deploy the MCP server.

### Podman

Podman is Red Hat's alternative to Docker with several key advantages:
- Does not require a daemon process
- Can run containers without root privileges (rootless containers)
- Better integration with systemd
- Compatible with Docker commands and Dockerfiles
- Native SELinux integration

Podman is the default container engine in Fedora, RHEL, and CentOS.

## Deployment with Docker

### Prerequisites

If you already have Docker and Docker Compose installed on your Fedora system:

```bash
# Verify Docker installation
docker --version
docker-compose --version
```

### Building and Running with Docker

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mcp-server.git
   cd mcp-server
   ```

2. Create your `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Build the Docker image:
   ```bash
   docker build -t mcp-server .
   ```

4. Run the container:
   ```bash
   docker run -d --name mcp-server -p 5000:5000 --env-file .env mcp-server
   ```

5. Check container logs:
   ```bash
   docker logs mcp-server
   ```

### Using Docker Compose

1. Create a `docker-compose.yml` file:
   ```yaml
   version: '3'
   services:
     mcp-server:
       build: .
       container_name: mcp-server
       ports:
         - "5000:5000"
       volumes:
         - ./data:/app/data
       env_file:
         - .env
       restart: unless-stopped
   ```

2. Start the service:
   ```bash
   docker-compose up -d
   ```

3. Check the service:
   ```bash
   docker-compose ps
   docker-compose logs
   ```

## Deployment with Podman

### Prerequisites

Podman comes pre-installed on Fedora. If you're using an older version:

```bash
# Install Podman
sudo dnf install -y podman

# Verify installation
podman --version
```

### Building and Running with Podman

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mcp-server.git
   cd mcp-server
   ```

2. Create your `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Build the container image:
   ```bash
   podman build -t mcp-server .
   ```

4. Run the container:
   ```bash
   podman run -d --name mcp-server -p 5000:5000 --env-file .env mcp-server
   ```

5. For SELinux-enabled systems, use the `:Z` volume mount flag for proper labeling:
   ```bash
   mkdir -p ./data
   podman run -d --name mcp-server -p 5000:5000 --env-file .env -v ./data:/app/data:Z mcp-server
   ```

6. Check container logs:
   ```bash
   podman logs mcp-server
   ```

### Using Podman Compose

1. Install Podman Compose:
   ```bash
   pip install podman-compose
   # or
   sudo dnf install podman-compose   # On Fedora 33+
   ```

2. Create a `docker-compose.yml` file (same as for Docker):
   ```yaml
   version: '3'
   services:
     mcp-server:
       build: .
       container_name: mcp-server
       ports:
         - "5000:5000"
       volumes:
         - ./data:/app/data:Z  # Note the :Z for SELinux
       env_file:
         - .env
       restart: unless-stopped
   ```

3. Start the service:
   ```bash
   podman-compose up -d
   ```

4. Check the service:
   ```bash
   podman-compose ps
   podman-compose logs
   ```

### Setting Up as a Systemd Service with Podman

Podman integrates well with systemd, allowing you to manage containers as systemd services:

1. Generate a systemd service file:
   ```bash
   mkdir -p ~/.config/systemd/user
   podman generate systemd --name mcp-server --files --new
   ```

2. Move the generated file to your user's systemd directory:
   ```bash
   mv container-mcp-server.service ~/.config/systemd/user/
   ```

3. Enable and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable container-mcp-server.service
   systemctl --user start container-mcp-server.service
   ```

4. Check the service status:
   ```bash
   systemctl --user status container-mcp-server.service
   ```

5. To allow the service to run even when you're not logged in:
   ```bash
   sudo loginctl enable-linger $USER
   ```

## Migrating from Docker to Podman on Fedora

If you're migrating from Docker to Podman on Fedora:

1. Make Podman use Docker Compose files:
   ```bash
   # Create an alias
   echo 'alias docker-compose="podman-compose"' >> ~/.bashrc
   source ~/.bashrc
   ```

2. Set up Docker compatibility:
   ```bash
   # Make docker command invoke podman
   echo 'alias docker="podman"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. Migrate existing containers (if needed):
   ```bash
   # Stop Docker services
   sudo systemctl stop docker
   
   # Pull the same images with Podman
   podman pull [your-images]
   
   # Create new containers using the same configurations
   podman run [your-container-configs]
   ```

## Container Configuration Tips

### Environment Variables

Both Docker and Podman support passing environment variables from a file:

```bash
# With Docker
docker run --env-file .env mcp-server

# With Podman
podman run --env-file .env mcp-server
```

### Persistent Storage

To persist data between container restarts:

```bash
# With Docker
docker run -v ./data:/app/data mcp-server

# With Podman on SELinux systems
podman run -v ./data:/app/data:Z mcp-server
```

### Resource Limits

Set CPU and memory limits for the container:

```bash
# With Docker
docker run --memory="1g" --cpus="1.0" mcp-server

# With Podman
podman run --memory="1g" --cpus="1.0" mcp-server
```

### Network Configuration

By default, the container exposes port 5000. If you need to use a different port:

```bash
# Map container port 5000 to host port 8080
docker run -p 8080:5000 mcp-server
# or
podman run -p 8080:5000 mcp-server
```

## Troubleshooting Container Deployments

### SELinux Issues

If you encounter permission denied errors on Fedora:

```bash
# Check SELinux denials
sudo ausearch -m avc -ts recent

# If needed, set the correct context for mounted volumes
sudo chcon -Rt container_file_t ./data
```

### Networking Issues

If you can't access the container from the host:

```bash
# Check if the container is running
podman ps

# Verify the port mapping
podman port mcp-server

# Check firewall rules
sudo firewall-cmd --list-all
```

### Resource Limitations

If the container is terminated unexpectedly:

```bash
# Check container logs
podman logs mcp-server

# Check system resources
podman stats

# Increase container memory limit
podman run --memory="2g" mcp-server
```

### Container Healthchecks

Add a healthcheck to your container:

```yaml
# In docker-compose.yml
services:
  mcp-server:
    build: .
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Conclusion

Both Docker and Podman provide robust container environments for deploying the MCP server. On Fedora and other Red Hat based systems, Podman offers better integration with system services and security features.

The main differences in deployment are:
- SELinux context handling with `:Z` volume mounts in Podman
- Rootless execution model in Podman
- Systemd integration in Podman
- Docker requires a daemon while Podman is daemonless

Choose the approach that best fits your existing infrastructure and security requirements.
