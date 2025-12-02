# Troubleshooting Guide - Spheraform

## Understanding the SSH Tunnel / Colima Issue

### What's Happening?

You're experiencing a **Docker port forwarding conflict** via Colima's SSH multiplexer.

### The Root Cause

1. **Colima uses SSH for networking**: Colima (which runs Docker on macOS) uses Lima, which creates a Linux VM. To communicate with this VM, Lima uses SSH with a multiplexer (mux).

2. **Automatic port forwarding**: When you run `docker-compose up -d`, Docker containers expose ports (like 5432 for PostgreSQL). Colima automatically forwards these ports from the VM to your Mac using SSH tunnels.

3. **The SSH process you see**: The SSH process listening on port 5432 is **NOT a separate tunnel** - it's Colima's SSH multiplexer forwarding the Docker PostgreSQL port!

   ```
   Your Mac (port 5432) → SSH Tunnel → Colima VM → Docker Container (port 5432)
   ```

4. **Why Colima "dies"**: When you kill the SSH process on port 5432, you're killing Colima's main networking process. This breaks Docker communication, making Colima appear dead.

### The Real Problem

You have **TWO PostgreSQL instances** competing for similar ports:

```bash
$ lsof -i -P | grep postgres
postgres  797  alexey  7u  IPv6  TCP localhost:5432 (LISTEN)  # <- Local PostgreSQL
ssh     31356  alexey  9u  IPv4  TCP *:5432 (LISTEN)        # <- Docker PostgreSQL via Colima
```

1. **Local PostgreSQL** (process 797) on port **5432**
2. **Docker PostgreSQL** (via Colima SSH tunnel) on port **5432**

## Solutions

### Solution 1: Use Different Port for Docker PostgreSQL (Recommended)

Change Docker to use a port that won't conflict:

```yaml
# docker-compose.yml
services:
  postgres:
    ports:
      - "5433:5432"  # Changed from 5432 to 5433
```

Then update your `.env`:
```bash
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5433/spheraform"
```

### Solution 2: Stop Local PostgreSQL

If you don't need the local PostgreSQL instance:

```bash
# macOS (if installed via Homebrew)
brew services stop postgresql

# Or if running manually
pkill -9 postgres
```

### Solution 3: Use Docker PostgreSQL Only

Keep Docker on 5432 and always use it:

```bash
# Make sure local PostgreSQL is stopped
brew services stop postgresql

# Use Docker PostgreSQL
DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform"
```

## Recommended Setup

**Best practice for Spheraform:**

1. **Stop local PostgreSQL** (you don't need it):
   ```bash
   brew services stop postgresql
   ```

2. **Keep Docker PostgreSQL on 5432**:
   ```yaml
   # docker-compose.yml (current setup)
   services:
     postgres:
       ports:
         - "5432:5432"
   ```

3. **Always use this connection string**:
   ```bash
   DATABASE_URL="postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform"
   ```

## How to Fix Current Issues

### Step 1: Check What's Running

```bash
# Check local PostgreSQL
lsof -i :5432

# Check Docker PostgreSQL (via Colima)
lsof -i :5432

# Check Colima status
colima status
```

### Step 2: Stop Local PostgreSQL

```bash
# If installed via Homebrew
brew services stop postgresql

# Verify it's stopped
lsof -i :5432
```

### Step 3: Restart Colima (Clean Start)

```bash
# Stop everything
docker-compose down
colima stop

# Start Colima fresh
colima start

# Start Docker services
docker-compose up -d postgres redis minio martin
```

### Step 4: Verify Port Forwarding

```bash
# You should see the SSH tunnel on 5432
lsof -i :5432

# This is CORRECT - it's Colima forwarding Docker PostgreSQL
```

### Step 5: Test Connection

```bash
# Test via Docker (should work)
docker exec spheraform-postgres psql -U spheraform -c "SELECT version();"

# Test via host (should work after port forwarding is established)
psql "postgresql://spheraform:spheraform_dev@localhost:5432/spheraform" -c "SELECT version();"
```

## Understanding Colima Networking

### What IS the SSH process?

```bash
$ lsof -i :5432
ssh  31356  alexey  9u  IPv4  TCP *:5432 (LISTEN)
```

**This SSH process is:**
- ✅ Part of Colima's networking layer
- ✅ Forwarding Docker container ports to your Mac
- ✅ Managed automatically by Lima/Colima
- ❌ NOT a separate SSH tunnel you created
- ❌ NOT something to kill manually

### What Happens When You Kill It?

```bash
kill 31356  # DON'T DO THIS!
```

**Result:**
1. ❌ Docker port forwarding breaks
2. ❌ You can't connect to Docker containers from your Mac
3. ❌ Docker commands may fail
4. ❌ Colima networking is broken

**Solution if you did this:**
```bash
colima stop
colima start
docker-compose up -d
```

## Prevention

### Add to Your Workflow

1. **Never kill Colima's SSH processes**
   - If port 5432 is busy, check if it's Colima
   - Don't kill SSH processes related to Colima

2. **Stop local PostgreSQL once**
   ```bash
   brew services stop postgresql
   ```

3. **Always use Docker PostgreSQL**
   - Port: 5432
   - Connection: `postgresql://spheraform:spheraform_dev@localhost:5432/spheraform`

4. **If port conflicts occur**
   ```bash
   # Check what's actually using the port
   lsof -i :5432

   # If it's NOT Colima SSH, then kill it
   # If it IS Colima SSH (ssh ... colima/ssh.sock [mux]), leave it alone!
   ```

## Quick Reference

### Identify Colima SSH Process

```bash
ps aux | grep ssh | grep colima
# This is Colima - DON'T KILL IT
```

### Identify Unwanted SSH Tunnel

```bash
lsof -i :5432
# If it shows: ssh -L 5432:...
# This is a manual tunnel - SAFE TO KILL

# If it shows: ssh: .../colima/ssh.sock [mux]
# This is Colima - DON'T KILL IT
```

### Restart Everything Cleanly

```bash
# 1. Stop Docker services
docker-compose down

# 2. Stop Colima
colima stop

# 3. Stop local PostgreSQL
brew services stop postgresql

# 4. Start Colima
colima start

# 5. Start Docker services
docker-compose up -d postgres redis minio martin

# 6. Verify
docker ps
lsof -i :5432
```

## Still Having Issues?

### Debug Checklist

- [ ] Local PostgreSQL stopped: `brew services stop postgresql`
- [ ] Colima running: `colima status` shows "Running"
- [ ] Docker working: `docker ps` shows containers
- [ ] Port 5432 forwarded by Colima SSH: `lsof -i :5432` shows ssh with colima/ssh.sock
- [ ] Can connect via Docker: `docker exec spheraform-postgres psql -U spheraform -c "SELECT 1;"`
- [ ] Can connect from host: `psql "postgresql://spheraform:spheraform_dev@localhost:5432/spheraform" -c "SELECT 1;"`

If all checks pass, proceed with the setup!

## Summary

**The Problem:**
- Colima uses SSH for Docker port forwarding
- You thought it was a separate tunnel and killed it
- This broke Colima's networking

**The Solution:**
- Stop local PostgreSQL: `brew services stop postgresql`
- Let Colima manage its own SSH processes
- Use Docker PostgreSQL on port 5432
- Never kill SSH processes with "colima/ssh.sock" in them

**The Key Insight:**
The SSH process on port 5432 is **part of Docker/Colima**, not an external tunnel!
