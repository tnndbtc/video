# BeatStitch Troubleshooting Guide

This guide covers common issues and their solutions.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Startup Issues](#startup-issues)
- [Upload Issues](#upload-issues)
- [Beat Detection Issues](#beat-detection-issues)
- [Timeline Issues](#timeline-issues)
- [Rendering Issues](#rendering-issues)
- [Queue and Worker Issues](#queue-and-worker-issues)
- [Memory Issues](#memory-issues)
- [Storage Issues](#storage-issues)
- [Authentication Issues](#authentication-issues)
- [Performance Issues](#performance-issues)

---

## Quick Diagnostics

### Check System Health

```bash
# Check health endpoint
curl http://localhost:8080/health

# Expected response:
# {"status": "healthy", "checks": {...}}
```

### Check Service Status

```bash
# View running containers
docker-compose ps

# Expected: all services "Up"
# NAME         STATUS
# frontend     Up
# backend      Up
# worker       Up
# redis        Up
```

### Check Logs

```bash
# All services
make logs

# Specific service
make logs-backend
make logs-worker
make logs-frontend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Common Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| Services not starting | `docker-compose down && make dev` |
| Database locked | `docker-compose restart backend` |
| Redis connection refused | `docker-compose restart redis` |
| Stale containers | `make clean && make dev` |

---

## Startup Issues

### Services Won't Start

**Symptoms:**
- `docker-compose up` fails
- Containers exit immediately

**Check:**

```bash
# View container logs
docker-compose logs

# Check for port conflicts
sudo lsof -i :3001
sudo lsof -i :8080
sudo lsof -i :6379
```

**Solutions:**

1. **Port in use:**
   ```bash
   # Find and kill process using the port
   sudo lsof -i :8080
   kill -9 <PID>
   ```

2. **Docker daemon not running:**
   ```bash
   sudo systemctl start docker
   ```

3. **Out of disk space:**
   ```bash
   docker system prune -a
   ```

4. **Permission issues:**
   ```bash
   sudo chown -R $USER:$USER .
   ```

### Backend Won't Start

**Symptoms:**
- Backend container exits with code 1
- "ModuleNotFoundError" in logs

**Solutions:**

1. **Rebuild the container:**
   ```bash
   docker-compose build backend
   docker-compose up backend
   ```

2. **Check environment variables:**
   ```bash
   # Verify .env exists and has required values
   cat .env | grep SECRET_KEY
   ```

3. **Database migration needed:**
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

### Worker Won't Connect to Redis

**Symptoms:**
- Worker logs show "Connection refused"
- Jobs stay in "queued" state

**Solutions:**

1. **Check Redis is running:**
   ```bash
   docker-compose ps redis
   docker-compose logs redis
   ```

2. **Restart Redis:**
   ```bash
   docker-compose restart redis
   docker-compose restart worker
   ```

3. **Check Redis URL:**
   ```bash
   # Should be redis://redis:6379/0 in Docker
   docker-compose exec worker env | grep REDIS
   ```

---

## Upload Issues

### Files Won't Upload

**Symptoms:**
- Upload fails with 413 error
- Upload hangs or times out

**Solutions:**

1. **Check file size limit:**
   ```bash
   # Default is 500MB
   # Check nginx config if using reverse proxy
   grep client_max_body_size /etc/nginx/sites-available/beatstitch
   ```

2. **For nginx, increase limit:**
   ```nginx
   # /etc/nginx/sites-available/beatstitch
   client_max_body_size 500M;
   proxy_read_timeout 300s;
   ```

3. **Check disk space:**
   ```bash
   df -h /var/lib/docker
   ```

### Unsupported File Type

**Symptoms:**
- Upload rejected with "unsupported file type"

**Supported types:**
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Videos: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`
- Audio: `.mp3`, `.wav`, `.flac`, `.aac`, `.m4a`, `.ogg`

**Solution:**

Convert file to supported format:

```bash
# Convert video to mp4
ffmpeg -i input.wmv -c:v libx264 -c:a aac output.mp4

# Convert audio to mp3
ffmpeg -i input.wma -c:a libmp3lame output.mp3
```

### Media Processing Stuck at "Pending"

**Symptoms:**
- Uploaded files stay in "pending" status
- Thumbnails never generate

**Solutions:**

1. **Check worker is running:**
   ```bash
   docker-compose ps worker
   ```

2. **Check worker logs:**
   ```bash
   make logs-worker
   ```

3. **Restart worker:**
   ```bash
   docker-compose restart worker
   ```

4. **Check Redis queue:**
   ```bash
   docker-compose exec redis redis-cli
   > KEYS beatstitch:*
   > LLEN beatstitch:thumbnails
   ```

---

## Beat Detection Issues

### Beat Detection Fails

**Symptoms:**
- Audio analysis fails with error
- "No beats detected" message

**Solutions:**

1. **Check audio file is valid:**
   ```bash
   # Verify with ffprobe
   ffprobe input.mp3
   ```

2. **Try re-analyzing:**
   ```bash
   curl -X POST http://localhost:8080/api/projects/{id}/audio/analyze \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Check worker logs for errors:**
   ```bash
   docker-compose logs worker | grep -i "beat\|error"
   ```

### Incorrect BPM Detection

**Symptoms:**
- Detected BPM doesn't match expected
- Cuts feel off-beat

**Possible causes:**
- Variable tempo in audio
- Complex rhythm or time signature
- Very slow or very fast tempo (outside 60-200 BPM range)

**Solutions:**

1. **Use audio with consistent tempo**

2. **Try different audio file with clearer beat**

3. **Adjust beats_per_cut setting:**
   ```json
   // If BPM is half of expected, use half the beats_per_cut
   {"beats_per_cut": 2}
   ```

### madmom Not Available

**Symptoms:**
- Log shows "madmom not available, using librosa fallback"
- Lower confidence beat detection

**This is expected behavior.** madmom has complex dependencies and may not install in all environments. librosa is the fallback and works reliably.

**To enable madmom (if needed):**

```dockerfile
# In worker/Dockerfile
RUN pip install madmom
```

---

## Timeline Issues

### Timeline Generation Fails

**Symptoms:**
- "Cannot generate timeline" error
- Precondition failed

**Check prerequisites:**

```bash
curl http://localhost:8080/api/projects/{id}/status \
  -H "Authorization: Bearer $TOKEN"
```

**Requirements:**
- At least 1 media asset with status "ready"
- Audio uploaded with analysis "complete"

**Solutions:**

1. **Wait for media processing:**
   - Check that all media shows "ready" status

2. **Wait for beat analysis:**
   - Check that audio shows "analysis_status": "complete"

3. **Re-upload failed media**

### Timeline Shows "Stale"

**Symptoms:**
- Timeline status shows `"stale": true`

**This means settings changed since timeline was generated.**

**Solution:**

Regenerate timeline:

```bash
curl -X POST http://localhost:8080/api/projects/{id}/timeline/generate \
  -H "Authorization: Bearer $TOKEN"
```

### Not Enough Beats

**Symptoms:**
- "Not enough beats to create timeline" error

**Solutions:**

1. **Use longer audio file** (recommended minimum: 30 seconds)

2. **Reduce beats_per_cut:**
   ```json
   {"beats_per_cut": 2}
   ```

---

## Rendering Issues

### Render Fails Immediately

**Symptoms:**
- Render job fails with "FFmpeg error"
- Output file is empty or missing

**Solutions:**

1. **Check FFmpeg is installed:**
   ```bash
   docker-compose exec worker ffmpeg -version
   ```

2. **Check file permissions:**
   ```bash
   docker-compose exec worker ls -la /data/uploads/{project_id}/
   ```

3. **Check disk space:**
   ```bash
   df -h
   ```

4. **Check worker logs:**
   ```bash
   docker-compose logs worker | grep -i ffmpeg
   ```

### Render Hangs or Times Out

**Symptoms:**
- Render progress stuck at certain percentage
- Job fails after 30 minutes

**Causes:**
- Very long video (>30 minutes output)
- Too many segments (>200)
- Memory exhaustion

**Solutions:**

1. **Reduce output quality for testing:**
   - Use preview render first

2. **Reduce segment count:**
   - Use higher beats_per_cut (e.g., 8 instead of 4)
   - Use shorter audio

3. **Increase worker memory:**
   ```yaml
   # docker-compose.yml
   services:
     worker:
       mem_limit: 8g
   ```

### "EDL Hash Mismatch" Error

**Symptoms:**
- Render fails with "Timeline has changed" error

**This means the timeline changed between starting render and actually rendering.**

**Solution:**

1. Fetch current timeline to get new edl_hash
2. Retry render with new edl_hash

```bash
# Get current hash
HASH=$(curl -s http://localhost:8080/api/projects/{id}/timeline \
  -H "Authorization: Bearer $TOKEN" | jq -r '.edl_hash')

# Retry render
curl -X POST http://localhost:8080/api/projects/{id}/render \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"type\": \"preview\", \"edl_hash\": \"$HASH\"}"
```

### FFmpeg "Invalid Input" Error

**Symptoms:**
- FFmpeg reports "Invalid data found when processing input"

**Solutions:**

1. **Re-upload corrupted media file**

2. **Convert media to standard format:**
   ```bash
   # Re-encode video
   ffmpeg -i input.mp4 -c:v libx264 -c:a aac output.mp4

   # Re-encode audio
   ffmpeg -i input.mp3 -c:a libmp3lame -q:a 2 output.mp3
   ```

3. **Check video codec compatibility:**
   ```bash
   ffprobe -v error -show_entries stream=codec_name input.mp4
   # Should be h264 for video, aac for audio
   ```

---

## Queue and Worker Issues

### Jobs Stuck in Queue

**Symptoms:**
- Jobs show "queued" status indefinitely
- No progress on jobs

**Solutions:**

1. **Check worker is running:**
   ```bash
   docker-compose ps worker
   ```

2. **Check worker is processing:**
   ```bash
   docker-compose logs worker --tail=50
   ```

3. **Restart worker:**
   ```bash
   docker-compose restart worker
   ```

4. **Clear stuck jobs (if needed):**
   ```bash
   docker-compose exec redis redis-cli
   > FLUSHDB
   ```
   **Warning:** This clears all queued jobs!

### Worker Crashes During Job

**Symptoms:**
- Worker container restarts
- Jobs fail with no error message

**Solutions:**

1. **Check for OOM (Out of Memory):**
   ```bash
   docker-compose logs worker | grep -i "killed\|oom"
   ```

2. **Increase memory limit:**
   ```yaml
   # docker-compose.yml
   services:
     worker:
       mem_limit: 8g
   ```

3. **Check system resources:**
   ```bash
   docker stats
   ```

### Jobs Disappear

**Symptoms:**
- Job was queued but can't find status

**Causes:**
- Worker crashed during job
- Redis restarted (losing queue)

**Solutions:**

1. **Enable Redis persistence:**
   ```yaml
   # docker-compose.yml
   redis:
     command: redis-server --appendonly yes
     volumes:
       - redis-data:/data
   ```

2. **Re-trigger the job:**
   - Re-upload audio for beat analysis
   - Re-generate timeline
   - Re-start render

---

## Memory Issues

### Out of Memory Errors

**Symptoms:**
- Container killed with exit code 137
- "Cannot allocate memory" errors

**Solutions:**

1. **Increase container memory:**
   ```yaml
   services:
     worker:
       mem_limit: 8g
   ```

2. **Process fewer concurrent jobs:**
   - Run single worker (default)

3. **Use smaller input files:**
   - Resize images before upload
   - Use shorter video clips

4. **Increase system swap:**
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

### Large Memory Usage

**Symptoms:**
- Memory usage grows over time
- System becomes slow

**Solutions:**

1. **Restart services periodically:**
   ```bash
   docker-compose restart worker
   ```

2. **Clean up old files:**
   ```bash
   # Clean temp files
   docker-compose exec worker rm -rf /data/temp/*
   ```

3. **Monitor memory:**
   ```bash
   docker stats --no-stream
   ```

---

## Storage Issues

### Out of Disk Space

**Symptoms:**
- "No space left on device" errors
- Uploads fail

**Solutions:**

1. **Check disk usage:**
   ```bash
   df -h
   du -sh /var/lib/docker/volumes/*
   ```

2. **Clean Docker:**
   ```bash
   docker system prune -a
   docker volume prune
   ```

3. **Clean old renders:**
   ```bash
   # Clean preview renders older than 24 hours
   find /data/outputs/*/preview -mtime +1 -delete

   # Clean temp files
   rm -rf /data/temp/*
   ```

4. **Clean orphaned files:**
   ```bash
   # Run cleanup script
   ./scripts/cleanup.sh
   ```

### Files Not Found

**Symptoms:**
- "File not found" errors during render
- Missing thumbnails

**Solutions:**

1. **Check file exists:**
   ```bash
   docker-compose exec backend ls -la /data/uploads/{project_id}/
   ```

2. **Check volume mount:**
   ```bash
   docker-compose exec backend df -h
   ```

3. **Verify volume configuration:**
   ```yaml
   # docker-compose.yml
   volumes:
     - beatstitch-data:/data
   ```

---

## Authentication Issues

### Invalid Token

**Symptoms:**
- 401 Unauthorized on all requests
- "Invalid or expired token" error

**Solutions:**

1. **Get new token:**
   ```bash
   curl -X POST http://localhost:8080/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"user","password":"pass"}'
   ```

2. **Check token expiration:**
   - Default is 24 hours
   - Re-login if expired

3. **Verify SECRET_KEY hasn't changed:**
   - Tokens become invalid if SECRET_KEY changes

### Can't Login

**Symptoms:**
- Login fails with valid credentials

**Solutions:**

1. **Check password case sensitivity**

2. **Reset password (if supported)**

3. **Create new account:**
   ```bash
   curl -X POST http://localhost:8080/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"newuser","password":"newpass123"}'
   ```

---

## Performance Issues

### Slow Uploads

**Solutions:**

1. **Check network:**
   ```bash
   # Test upload speed
   curl -o /dev/null -w "Speed: %{speed_upload}\n" \
     -X POST -F "file=@test.mp4" http://localhost:8080/api/upload
   ```

2. **Disable proxy buffering:**
   ```nginx
   proxy_request_buffering off;
   ```

3. **Use chunked uploads for large files**

### Slow Renders

**Solutions:**

1. **Use preview first** (faster settings)

2. **Reduce output resolution:**
   ```json
   {"output_width": 1280, "output_height": 720}
   ```

3. **Increase CPU allocation:**
   ```yaml
   services:
     worker:
       deploy:
         resources:
           limits:
             cpus: '4'
   ```

4. **Use SSD storage**

### Slow API Responses

**Solutions:**

1. **Check database:**
   ```bash
   # Vacuum SQLite
   docker-compose exec backend python -c "
   import sqlite3
   conn = sqlite3.connect('/data/db/beatstitch.db')
   conn.execute('VACUUM')
   conn.close()
   "
   ```

2. **Check Redis:**
   ```bash
   docker-compose exec redis redis-cli INFO
   ```

3. **Enable caching** (if not already)

---

## Getting Help

If you can't resolve an issue:

1. **Gather information:**
   ```bash
   # System info
   docker-compose version
   docker version

   # Service logs
   docker-compose logs > logs.txt

   # Health check
   curl http://localhost:8080/health > health.json
   ```

2. **Check GitHub Issues** for similar problems

3. **Open new issue** with:
   - Steps to reproduce
   - Error messages
   - Logs (sanitize sensitive data)
   - Environment details
