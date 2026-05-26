# Applegarth Health and Safety — Client Portal

A full-stack client portal built with Python (Tornado), SQLite, and plain HTML/JS.
No external database required. Runs on any Linux server or cloud platform.

---

## Features

**Clients**
- Self-register (pending admin approval)
- Log in and view their compliance dashboard
- See all their assessments with live status (Current / Due soon / Overdue)
- Download uploaded reports and documents
- Compliance score calculated automatically from review dates

**Admin (Jeremy)**
- Approve or reject new registrations
- Overview of all clients with compliance scores
- Add assessments to any client account
- Upload PDFs and documents linked to assessments
- Set review dates (triggers status changes automatically)
- Add and resolve action items per assessment

---

## Running locally

### Requirements
- Python 3.9+
- The following packages (all standard on Ubuntu 22+):
  - `tornado`
  - `bcrypt`

### Install & start

```bash
# Check Python is installed
python3 --version

# Install dependencies if needed
pip install tornado bcrypt --break-system-packages

# Start the server
python3 server.py
```

Visit: http://localhost:8080

**First-time admin login:**
- Email: `info@applegarthhealthandsafety.co.uk`
- Password: `admin123`

**IMPORTANT: Change the admin password immediately after first login.**
(Currently, password changes must be done via a one-time script — see below.
A "change password" feature can be added to the admin panel on request.)

### Change the admin password

```bash
python3 - <<'EOF'
import sqlite3, bcrypt, pathlib
pw = input("New password: ").encode()
h = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
conn = sqlite3.connect(str(pathlib.Path("portal.db")))
conn.execute("UPDATE users SET password_hash = ? WHERE is_admin = 1", [h])
conn.commit()
print("Password updated.")
EOF
```

---

## Deploying to Railway (recommended — free tier available)

1. Push this folder to a GitHub repository.
2. Go to https://railway.app and create a new project → Deploy from GitHub.
3. Select your repo. Railway will detect Python automatically.
4. Set the start command to: `python3 server.py`
5. Set the PORT environment variable if needed (the app reads `$PORT`).
6. Railway assigns you a public URL like `https://yourapp.up.railway.app`.

**Important:** Railway's free tier does not persist files between deploys.
For a production deployment, either:
- Use Railway's persistent volume mount (paid), or
- Use Render (see below) which includes a persistent disk.

---

## Deploying to Render (recommended for persistence)

1. Push this folder to GitHub.
2. Go to https://render.com → New → Web Service.
3. Connect your GitHub repo.
4. Set:
   - **Build command:** `pip install tornado bcrypt`
   - **Start command:** `python3 server.py`
5. Add a **Disk** (under Advanced) mounted at `/opt/render/project/src` — this
   persists both `portal.db` (the database) and the `uploads/` folder.
6. Set the environment variable `PORT=8080` (or leave blank; Render sets it).

---

## Deploying to a VPS (DigitalOcean, Linode, Hetzner, etc.)

```bash
# On your server (Ubuntu 22):
apt update && apt install -y python3 python3-pip

# Clone or upload your project
git clone https://github.com/yourname/applegarth-portal /opt/applegarth-portal
cd /opt/applegarth-portal
pip install tornado bcrypt --break-system-packages

# Run as a systemd service (keeps it running after reboots)
cat > /etc/systemd/system/applegarth.service <<EOF
[Unit]
Description=Applegarth Portal
After=network.target

[Service]
WorkingDirectory=/opt/applegarth-portal
ExecStart=python3 server.py
Restart=always
Environment=PORT=8080

[Install]
WantedBy=multi-user.target
EOF

systemctl enable applegarth
systemctl start applegarth

# Then set up Nginx as a reverse proxy on port 80/443
# and use Certbot for a free SSL certificate.
```

---

## Adding the portal link to your website

Once deployed, add a "Client Login" link to your website navigation:

```html
<a href="https://portal.applegarthhealthandsafety.co.uk">Client portal</a>
```

You can host it on a subdomain (e.g. `portal.applegarthhealthandsafety.co.uk`) by
pointing that subdomain's DNS A record to your server IP, then configuring Nginx.

---

## Customisation notes

- **Branding colours** are defined in each HTML file's `<style>` block.
  The primary dark green is `#1a2e1a`, the accent green is `#2e7d3a`.
- **"Request assessment" button** opens a pre-filled email to Jeremy.
  Change the email address in `dashboard.html` if needed.
- **Review window (due-soon threshold):** Currently 90 days. Change in `server.py`
  inside the `assessment_status()` function.
- **Compliance score formula:** Defined in `server.py` in `calc_score()`.
  Currently: Current=100pts, Due soon=60pts, Overdue=0pts, minus 5 per open action item.

---

## File structure

```
applegarth-portal/
├── server.py          # Tornado web server + all API handlers
├── db.py              # SQLite setup and admin seed
├── package.json       # (reference only — Python project)
├── README.md          # This file
├── portal.db          # Created on first run — the database
├── .secret            # Created on first run — cookie signing key
├── uploads/           # Uploaded documents stored here
└── public/
    ├── login.html
    ├── register.html
    ├── dashboard.html  # Client portal
    └── admin.html      # Admin panel
```

---

## Support

This portal was designed and built specifically for Applegarth Health and Safety.
For additions or modifications, contact the developer.
