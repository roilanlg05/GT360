# GT360 Backend Deployment Process

**Last Updated:** 2026-01-28
**Deployment Method:** Docker Compose
**Environment:** Production

---

## 📋 Table of Contents

1. [System Architecture](#system-architecture)
2. [Prerequisites](#prerequisites)
3. [Standard Deployment Process](#standard-deployment-process)
4. [Verification Steps](#verification-steps)
5. [Rollback Procedure](#rollback-procedure)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## 🏗️ System Architecture

### Docker Compose Services

The GT360 application runs as a Docker Compose stack with 4 services:

| Service | Container Name | Port | Description |
|---------|---------------|------|-------------|
| **app** | gt360 | 8000 | Main FastAPI backend application |
| **postgres** | postgres | 5432 | PostgreSQL 18.1 database |
| **redis** | redis-service | 6379 | Redis cache and pub/sub |
| **streaming** | gt360-streaming-1 | - | Trip streaming service |

### Key Files

```
GT360/
├── docker-compose.yml          # Service orchestration
├── Dockerfile                  # Backend app image definition
├── requirements.txt            # Python dependencies
├── main.py                     # FastAPI application entrypoint
├── .env                        # Environment variables (not in git)
└── services/
    └── streaming/
        └── Dockerfile          # Streaming service image
```

---

## ✅ Prerequisites

Before deploying, ensure you have:

- [x] Docker Engine installed and running
- [x] Docker Compose installed
- [x] Access to the server (SSH or direct)
- [x] `.env` file with correct environment variables
- [x] Latest code changes committed/pulled

### Check Docker Status

```bash
# Verify Docker is running
docker --version
docker-compose --version

# Check current containers
docker ps
```

---

## 🚀 Standard Deployment Process

### Step 1: Navigate to Project Directory

```bash
cd /home/backend/GT360
```

### Step 2: Pull Latest Changes (if using Git)

```bash
git pull origin main
# or whichever branch you're deploying from
```

### Step 3: Rebuild Docker Image

This step builds a new Docker image with your latest code changes.

```bash
docker-compose build app
```

**Expected Output:**
```
#11 [6/8] COPY . /app
#11 DONE 15.4s

#14 exporting to image
#14 DONE 3.1s

 gt360:latest  Built
```

**Time:** ~30-60 seconds depending on code changes

### Step 4: Recreate Container

This stops the old container and starts a new one with the rebuilt image.

```bash
docker-compose up -d app
```

**Expected Output:**
```
 Container gt360  Recreate
 Container gt360  Recreated
 Container gt360  Starting
 Container gt360  Started
```

**Note:** The `-d` flag runs the container in detached mode (background).

### Step 5: Verify Deployment

Wait a few seconds for the application to start, then verify:

```bash
# Check container is running
docker ps | grep gt360

# Check logs for errors
docker logs gt360 --tail 50

# Test API endpoint
curl http://localhost:8000/docs
```

**Success Indicators:**
- ✅ Container status shows "Up X seconds/minutes"
- ✅ No ERROR messages in logs
- ✅ API responds with 200 OK

---

## 🔍 Verification Steps

### 1. Container Health Check

```bash
# Check all containers are running
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected:
```
NAMES               STATUS              PORTS
gt360               Up X minutes        0.0.0.0:8000->8000/tcp
postgres            Up X days           0.0.0.0:5432->5432/tcp
redis-service       Up X days           0.0.0.0:6379->6379/tcp
gt360-streaming-1   Up X days
```

### 2. Application Logs

```bash
# View recent logs
docker logs gt360 --tail 100

# Follow logs in real-time
docker logs gt360 -f
```

Look for:
- ✅ No Python exceptions or stack traces
- ✅ Database connections successful
- ✅ API requests being processed

### 3. API Endpoint Test

```bash
# Test docs endpoint (should return HTML)
curl -I http://localhost:8000/docs

# Expected: HTTP/1.1 200 OK
```

### 4. Database Connectivity

```bash
# Check if app can connect to database
docker logs gt360 --tail 100 | grep -i "database\|postgres\|connection"
```

### 5. Code Changes Verification

If you made specific code changes, verify they're active:

```bash
# Example: Check if a specific log message appears
docker logs gt360 --tail 200 | grep "YOUR_NEW_LOG_MESSAGE"
```

---

## 🔄 Rollback Procedure

If the deployment has issues, you can rollback to the previous version.

### Option 1: Quick Rollback (Restart Previous Container)

If the previous container still exists:

```bash
# List all containers (including stopped)
docker ps -a | grep gt360

# Start the previous container
docker start <previous_container_id>

# Stop the current one
docker stop gt360
```

### Option 2: Full Rollback (Rebuild Previous Version)

```bash
# 1. Checkout previous code version
git checkout <previous_commit_hash>

# 2. Rebuild image
docker-compose build app

# 3. Recreate container
docker-compose up -d app

# 4. Verify
docker logs gt360 --tail 50
```

### Option 3: Use Previous Docker Image

```bash
# List image history
docker images gt360

# Tag previous image as latest
docker tag gt360:<previous_tag> gt360:latest

# Recreate container
docker-compose up -d app
```

---

## 🛠️ Troubleshooting

### Issue: Container Won't Start

**Symptoms:**
- Container status shows "Restarting" or "Exited"

**Solution:**
```bash
# Check logs for errors
docker logs gt360 --tail 100

# Common issues:
# - Port 8000 already in use
# - Database connection failed
# - Missing environment variables
```

### Issue: Port Already in Use

**Error:** `bind: address already in use`

**Solution:**
```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill the process
sudo kill -9 <PID>

# Or stop the conflicting container
docker stop <container_using_port>
```

### Issue: Database Connection Failed

**Symptoms:**
- Logs show "could not connect to server"

**Solution:**
```bash
# Check if postgres container is running
docker ps | grep postgres

# Restart postgres if needed
docker-compose restart postgres

# Wait a few seconds, then restart app
docker-compose restart app
```

### Issue: Code Changes Not Reflected

**Symptoms:**
- Old code still running after deployment

**Solution:**
```bash
# Force rebuild without cache
docker-compose build --no-cache app

# Remove old image
docker rmi gt360:latest

# Rebuild and restart
docker-compose build app
docker-compose up -d app
```

### Issue: Out of Disk Space

**Error:** `no space left on device`

**Solution:**
```bash
# Clean up unused Docker resources
docker system prune -a

# Remove old/dangling images
docker image prune -a

# Check disk usage
df -h
```

---

## 📚 Best Practices

### 1. Always Check Logs After Deployment

```bash
# Monitor logs for at least 1-2 minutes after deployment
docker logs gt360 -f
```

### 2. Deploy During Low Traffic Periods

- Best time: Late night or early morning
- Avoid peak business hours
- Notify team before deployment

### 3. Keep Backups

```bash
# Backup database before major changes
docker exec postgres pg_dump -U gt360 gt360 > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 4. Test in Staging First

If available, always test deployments in staging environment before production.

### 5. Use Git Tags for Releases

```bash
# Tag release before deploying
git tag -a v1.0.1 -m "Fixed revert flags bug"
git push origin v1.0.1
```

### 6. Document Changes

Keep a changelog of what was deployed:
- Date and time
- Code changes included
- Any database migrations run
- Issues encountered

### 7. Monitor After Deployment

- Check error logs: `docker logs gt360 | grep ERROR`
- Monitor API response times
- Watch for unusual activity
- Verify frontend functionality

---

## 🔐 Environment Variables

Critical environment variables (in `.env` file):

```bash
# Database
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_DB=gt360
POSTGRES_USER=gt360
POSTGRES_PASSWORD=<secure_password>

# Application
JWT_SECRET_KEY=<secret_key>
WEBHOOK_SECRET=<webhook_secret>

# External Services
BREVO_KEY=<brevo_api_key>
```

**Security:** Never commit `.env` file to git!

---

## 📊 Deployment Checklist

Use this checklist for every deployment:

- [ ] Latest code pulled/committed
- [ ] Environment variables configured
- [ ] Dependencies updated in requirements.txt
- [ ] Database migrations prepared (if any)
- [ ] Staging tested (if available)
- [ ] Team notified
- [ ] Backup created
- [ ] Build image: `docker-compose build app`
- [ ] Deploy: `docker-compose up -d app`
- [ ] Verify logs: `docker logs gt360 --tail 100`
- [ ] Test endpoints: `curl http://localhost:8000/docs`
- [ ] Monitor for 5-10 minutes
- [ ] Document deployment in changelog
- [ ] Notify team of completion

---

## 🚨 Emergency Contacts

If deployment fails and you need help:

1. Check this document first
2. Review logs: `docker logs gt360`
3. Check #engineering Slack channel
4. Contact DevOps team

---

## 📝 Deployment History Log

Keep track of deployments:

| Date | Version | Changes | Deployed By | Status |
|------|---------|---------|-------------|--------|
| 2026-01-28 | v2.0.1 | Fixed revert flags bug + preview duplicates | Claude | ✅ Success |
| (previous) | ... | ... | ... | ... |

---

## 🎓 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [PostgreSQL Docker Guide](https://hub.docker.com/_/postgres)

---

**Version:** 1.0
**Last Reviewed:** 2026-01-28
**Owner:** DevOps Team
