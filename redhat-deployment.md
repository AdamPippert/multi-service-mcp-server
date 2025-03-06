# MCP Server Deployment Guide for Red Hat Environments

This guide covers deploying the Model Context Protocol (MCP) server on Red Hat based environments including RHEL, CentOS, and Fedora.

## Prerequisites

- Red Hat Enterprise Linux 8/9, CentOS Stream 8/9, or Fedora 35+
- `podman` or `docker` installed
- Python 3.8+ and pip
- Node.js 14+ and npm
- Git

## Installation Methods

There are several ways to deploy the MCP server in a Red Hat environment:

1. Direct deployment on the host
2. Containerized deployment using Podman (Red Hat's container engine)
3. Deployment on OpenShift (Red Hat's Kubernetes platform)

## Method 1: Direct Deployment

### Install Dependencies

```bash
# Install Python and Node.js
sudo dnf install -y python39 python39-devel python39-pip nodejs npm

# Install development tools (for building Python extensions)
sudo dnf group install -y "Development Tools"

# Install Chromium (for Puppeteer)
sudo dnf install -y chromium
```

### Set Up the MCP Server

```bash
# Clone the repository
git clone https://github.com/yourusername/mcp-server.git
cd mcp-server

# Create a Python virtual environment
python3.9 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install

# Create .env file with your configuration
cat > .env << EOF
SECRET_KEY=your-secret-key
DEBUG=False

# GitHub configuration
GITHUB_TOKEN=your-github-token

# GitLab configuration
GITLAB_TOKEN=your-gitlab-token

# Google Maps configuration
GMAPS_API_KEY=your-google-maps-api-key

# Memory configuration
MEMORY_DB_URI=sqlite:///memory.db

# Puppeteer configuration
PUPPETEER_HEADLESS=true
CHROME_PATH=/usr/bin/chromium-browser
EOF

# Run the server
python app.py
```

### Setting Up as a Systemd Service

To run the MCP server as a background service:

```bash
# Create a systemd service file
sudo tee /etc/systemd/system/mcp-server.service > /dev/null << EOF
[Unit]
Description=MCP Server
After=network.target

[Service]
User=mcp
WorkingDirectory=/opt/mcp-server
ExecStart=/opt/mcp-server/venv/bin/python /opt/mcp-server/app.py
Restart=on-failure
Environment=PATH=/opt/mcp-server/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/opt/mcp-server/.env

[Install]
WantedBy=multi-user.target
EOF

# Create a dedicated user for the service
sudo useradd -r -s /bin/false mcp

# Set up the application directory
sudo mkdir -p /opt/mcp-server
sudo cp -r * /opt/mcp-server/
sudo cp .env /opt/mcp-server/
sudo chown -R mcp:mcp /opt/mcp-server

# Enable and start the service
sudo systemctl enable mcp-server
sudo systemctl start mcp-server
sudo systemctl status mcp-server
```

## Method 2: Containerized Deployment with Podman

Podman is Red Hat's container engine, compatible with Docker commands but with added security features.

### Building and Running the Container

```bash
# Build the container image
podman build -t mcp-server .

# Create a directory for persistent data
mkdir -p ~/mcp-data

# Run the container
podman run --name mcp-server \
  -p 5000:5000 \
  -v ~/mcp-data:/app/data \
  --env-file .env \
  -d mcp-server
```

### Setting Up as a Systemd Service with Podman

```bash
# Generate a systemd service file for the container
mkdir -p ~/.config/systemd/user
podman generate systemd --name mcp-server --files --new

# Move the generated file
mv container-mcp-server.service ~/.config/systemd/user/

# Enable linger for your user (allows services to run without being logged in)
sudo loginctl enable-linger $USER

# Enable and start the service
systemctl --user enable container-mcp-server.service
systemctl --user start container-mcp-server.service
systemctl --user status container-mcp-server.service
```

## Method 3: Deployment on OpenShift

OpenShift is Red Hat's enterprise Kubernetes platform.

### Prerequisites

- Access to an OpenShift cluster
- OpenShift CLI (`oc`) installed and configured
- Container image pushed to a registry accessible from OpenShift

### Deploying to OpenShift

1. Create a new project:

```bash
oc new-project mcp-server
```

2. Create a ConfigMap for configuration:

```bash
oc create configmap mcp-config \
  --from-literal=DEBUG=False \
  --from-literal=CHROME_PATH=/usr/bin/chromium-browser \
  --from-literal=PUPPETEER_HEADLESS=true
```

3. Create secrets for sensitive data:

```bash
oc create secret generic mcp-secrets \
  --from-literal=SECRET_KEY=your-secret-key \
  --from-literal=GITHUB_TOKEN=your-github-token \
  --from-literal=GITLAB_TOKEN=your-gitlab-token \
  --from-literal=GMAPS_API_KEY=your-google-maps-api-key
```

4. Create a YAML file for the deployment:

```yaml
# mcp-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
  labels:
    app: mcp-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: your-registry/mcp-server:latest
        ports:
        - containerPort: 5000
        envFrom:
        - configMapRef:
            name: mcp-config
        - secretRef:
            name: mcp-secrets
        volumeMounts:
        - name: mcp-data
          mountPath: /app/data
      volumes:
      - name: mcp-data
        persistentVolumeClaim:
          claimName: mcp-data-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
spec:
  selector:
    app: mcp-server
  ports:
  - port: 80
    targetPort: 5000
  type: ClusterIP
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mcp-data-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: mcp-server
spec:
  to:
    kind: Service
    name: mcp-server
  port:
    targetPort: 5000
```

5. Apply the deployment:

```bash
oc apply -f mcp-deployment.yaml
```

6. Verify the deployment:

```bash
oc get pods
oc get routes
```

The route URL will be the publicly accessible endpoint for your MCP server.

## Security Considerations

### SELinux Configuration

Red Hat systems use SELinux by default. If you're running the server directly:

```bash
# For the direct deployment method
sudo semanage fcontext -a -t httpd_sys_content_t "/opt/mcp-server(/.*)?"
sudo restorecon -Rv /opt/mcp-server

# If using socket connections
sudo setsebool -P httpd_can_network_connect 1
```

### Firewall Configuration

```bash
# Open the port in the firewall
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

## Monitoring and Logging

### Setting up Prometheus Monitoring

1. Install the Prometheus client for Python:

```bash
pip install prometheus-client
```

2. Add Prometheus metrics to the MCP server (add to app.py).

### Configuring Logging with rsyslog

1. Create a rsyslog configuration:

```bash
sudo tee /etc/rsyslog.d/mcp-server.conf > /dev/null << EOF
if \$programname == 'mcp-server' then /var/log/mcp-server.log
& stop
EOF
```

2. Restart rsyslog:

```bash
sudo systemctl restart rsyslog
```

## Performance Tuning

### Running with gunicorn

For production environments, use gunicorn:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

Update the systemd service file to use gunicorn instead of direct Python execution.

## Troubleshooting

### Common Issues and Solutions

1. **SELinux denials**:
   - Check audit logs: `sudo ausearch -m avc -ts recent`
   - Create a policy module: `sudo audit2allow -a -M mcp-server`
   - Apply the policy: `sudo semodule -i mcp-server.pp`

2. **Puppeteer/Chrome issues**:
   - Ensure Chromium is installed: `sudo dnf install chromium`
   - Check for missing dependencies: `ldd /usr/bin/chromium-browser`
   - Install additional libraries if needed: `sudo dnf install libXcomposite libXcursor libXi libXtst cups-libs libXScrnSaver alsa-lib pango at-spi2-atk gtk3`

3. **Node.js compatibility**:
   - If you need a newer Node.js version than what's in the repositories:
   ```bash
   # Install Node.js 16.x
   sudo dnf module reset nodejs
   sudo dnf module enable nodejs:16
   sudo dnf install nodejs
   ```

For any other issues, check the logs:
```bash
sudo journalctl -u mcp-server.service
```

## Conclusion

This deployment guide provides multiple methods for deploying the MCP server on Red Hat environments. Choose the method that best fits your infrastructure and operational requirements.

For further assistance, refer to the Red Hat documentation or open an issue in the MCP server repository.
