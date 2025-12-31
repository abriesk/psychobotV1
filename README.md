# Psychotherapy Booking Bot V1.0 (In work curently)

Telegram bot for psychotherapists to manage client bookings: online/onsite, individual/couple sessions, time negotiation, waitlist, and admin tools. Now with webUI for clients and admin. NPM to register your domain and request certificate. Added ability to add aditional languages from web admin UI.
# Psychotherapy Booking Bot v1.0.X

A hybrid booking management system for psychotherapists combining a Telegram Bot interface with a modern Web UI. Designed to handle scheduling, client negotiations, content management, and multi-language support efficiently.

## 🚀 New in v1.0.X
* **Web Admin Dashboard:** Full graphical interface to manage bookings, content, and settings.
* **Web Client Booking:** Clients can now book slots directly via a web interface in addition to the Telegram bot.
* **Dynamic Content:** Add languages and edit translations directly from the database without code changes.
* **Flexible Infrastructure:** Native Docker support for both Nginx Proxy Manager and Cloudflare Tunnel.

## Features

### 🤖 For Clients
* **Dual Interface:** Book via Telegram chat flow or a clean Web UI.
* **Smart Booking:** View available slots, request specific times, or join a waitlist.
* **Multi-Language:** Interface available in Russian, Armenian, and easily extensible to others via the Admin Panel.
* **Info Hub:** Access HTML landing pages (Terms, Qualifications, About) directly within the bot.

### 🛠 For Therapists (Admin)
* **Web Dashboard:**
    * **Slot Management:** Create, hold, and release appointment slots visually.
    * **Request Handling:** Approve, reject, or propose alternative times for booking requests.
    * **Content Management:** Edit "Landing" pages (HTML) and system translations on the fly.
    * **Settings:** Configure timezones, prices, and languages.
* **Telegram Admin Tools:** Quick toggles for availability, immediate request notifications, and basic management commands.
* **Negotiation History:** Full log of proposals and counter-proposals stored in PostgreSQL.

### ⚙️ Technical Highlights
* **Backend:** Python 3.10+ (Aiogram 3.x + FastAPI).
* **Database:** PostgreSQL 15 with SQLAlchemy & Alembic migrations.
* **Deployment:** Docker Compose with **Profiles** for easy proxy switching.
* **Security:** Environment-based configuration, hidden internal ports.

---

## Quick Start (Docker)

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/abriesk/psychobot.git](https://github.com/abriesk/psychobotV1.git)
    cd psychobot
    ```

2.  **Configure Environment:**
    Create a `.env` file (see provided example) with your credentials:
    ```env
    BOT_TOKEN=your_token
    ADMIN_IDS=123456789
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=secret
    
    # Choose your proxy profile: 'npm' or 'cloudflare'
    COMPOSE_PROFILES=npm
    # TUNNEL_TOKEN=ey... (Required if using cloudflare)
    ```

3.  **Run with Docker:**
    The system uses Docker profiles to launch the appropriate proxy service.
    ```bash
    docker compose up --build -d
    ```

4.  **Access:**
    * **Telegram:** Start your bot via the Telegram app.
    * **Web Admin:** Access via `https://your-domain.com/admin` (configured via NPM or Cloudflare).

---

## Configuration & Customization

* **Proxy Switching:**
    Change the `COMPOSE_PROFILES` variable in `.env` to switch between Nginx Proxy Manager (`npm`) and Cloudflare Tunnel (`cloudflare`). No manual container manipulation required.
    
* **Adding Languages:**
    Go to the Web Admin Panel → **Languages** → Add New. The system automatically handles database migration for new translation keys.

* **Landing Pages:**
    Upload HTML files via the Web Admin Panel or the Telegram `/admin` menu.

---

## Credits & Contribution

This project was born from a real need and built collaboratively with the help of several LLMs under human direction.

* **Concept & Core Strategy:** Ab (Горилла in Chief 🦍)
* **Grok (xAI):** Technical requirements compilation.
* **Gemini (Google):** Generated the initial MVP architectural foundation for v0.8, core Python handlers, and performed final system-wide code reviews for version 0.8, bug fixes for v1.0, and cloudflared update.
* **Claude (Anthropic):** Gap analysis, feature implementation, and critical UX fixes for v0.8, most works on UI and backend code for update to v1.0.X.

Pull requests are welcome!

Here is the expanded, beginner-friendly version of the "Home Hosting" guide.

I have broken it down into very specific actions (like "Look for the whale icon" or "Open Notepad") to remove any ambiguity for someone who has never used a terminal before.

You can add this to your README.md or as a separate guide.
🏠 Home Hosting Guide: Run on Your Laptop/Desktop

Who is this for? Therapists who want to own their data and run the bot from their own computer (Windows or Mac) without paying for a cloud server or needing complex IT skills.

Requirements:

    A computer that stays ON and connected to the internet during the hours you want clients to book.

    A free Cloudflare account.

    A domain name (e.g., doctor-name.com).

Phase 1: Install the Software

    Download Docker Desktop:

        Go to docker.com/products/docker-desktop and download the version for your computer (Windows or Mac).

        Install it just like any other program.

        Crucial Step: Once installed, open the "Docker Desktop" application. You should see a little whale icon in your taskbar (near the clock). Docker must be running for your bot to work.

    Download the Bot Code:

        Click the green Code button on this GitHub page and select Download ZIP.

        Extract (unzip) the folder to somewhere easy to find, like your Desktop or Documents. Rename the folder to psychobot.

Phase 2: Connect Your Domain (Cloudflare)

This step creates a secure "tunnel" so the internet can talk to your computer without you needing to mess with router settings.

    Create a Tunnel:

        Log in to the Cloudflare Zero Trust Dashboard.

        On the left menu, click Networks → Tunnels.

        Click the blue Create a Tunnel button.

        Select Cloudflared (connector type) and click Next.

        Name your tunnel (e.g., my-bot) and click Save Tunnel.

    Get the Secret Token:

        You will see a screen with installation commands for different operating systems.

        Look for the box with the code. You don't need the whole command, just the long string of random letters and numbers following the word token:.

        Copy that long string and save it somewhere safe for a moment.

    Point the Tunnel to Your Bot:

        Click Next at the bottom of the Cloudflare page.

        Public Hostname:

            Subdomain: Leave blank (or type www).

            Domain: Select your domain (e.g., doctor-name.com).

        Service:

            Type: Select HTTP.

            URL: Type web:8000.

        Click Save Tunnel.

Phase 3: Configure the Bot

    Open the Config File:

        Go to the psychobot folder you unzipped earlier.

        Look for a file named .env.

            Note: If you don't see it, look for .env.example, make a copy of it, and rename the copy to .env.

        Right-click the .env file and choose Open with → Notepad (Windows) or TextEdit (Mac).

    Update the Settings:

        Find the line that says COMPOSE_PROFILES=npm. Change it to:
        Ini, TOML

COMPOSE_PROFILES=cloudflare

Find the line TUNNEL_TOKEN=. Paste the long code you copied from Cloudflare:
Ini, TOML

        TUNNEL_TOKEN=eyJhIjoi... (paste your long token here)

        Make sure your BOT_TOKEN (from Telegram) and ADMIN_IDS are also filled in.

        Save the file and close it.

Phase 4: Start the Bot

    Open the Terminal:

        Windows: Open the psychobot folder. In the address bar at the top (where it says C:\Users\...), click, type cmd, and hit Enter. A black window should appear.

        Mac: Open "Terminal". Type cd (with a space), drag the psychobot folder into the window, and hit Enter.

    Run the Start Command: Type this exact command and press Enter:
    Bash

    docker compose up -d

    Wait:

        You will see lines of text saying "Pulling..." and "Downloading...". This is normal; it's downloading the necessary software.

        Once it says "Started" or "Healthy", you are done!

🎉 Your bot is now live! Try sending /start to your bot in Telegram.
❓ Common Questions

How do I stop it? Open the terminal in the folder again and run: docker compose down.

What if I restart my computer?

    Make sure Docker Desktop starts (look for the whale icon).

    Open the terminal in the folder and run docker compose up -d again.

Do I need to keep the black window open? No. Once the command finishes, you can close the terminal window. The bot runs quietly in the background (inside Docker).

(foloowing description right now copy-pasted from v0.8)
## Features

- Multi-language interface (Russian + Armenian, easy to extend)
- Booking flow: type (individual/couple), format (online/onsite), timezone, desired time, problem description
- Flexible time negotiation (client ↔ therapist proposals/counter-proposals)
- Waitlist mode when availability is off
- Admin panel:
  - Toggle availability
  - View/manage pending requests (approve, propose alt time, reject)
  - Edit prices (displayed in buttons)
  - Upload HTML landing pages (terms, qualification, about therapy, references)
- Persistent main menu with "Home" button
- Docker-ready with PostgreSQL
- Full negotiation history stored in DB

## Quick Start (Docker)

1. Clone the repo:
   ```bash
   git clone https://github.com/abriesk/psychobot.git
   cd psychobot
2. Create or edit .env file:
   BOT_TOKEN=your_telegram_bot_token_here
   ADMIN_IDS=123456789,987654321  # your Telegram user IDs, comma-separated
   DEFAULT_LANGUAGE=ru
   CLINIC_ONSITE_LINK=https://example-clinic.com/booking
   POSTGRES_DB=psychobot
   POSTGRES_USER=postgres
3. Build and run:
   docker compose up --build -d
4. Start chatting with your bot and run /start. Admin commands appear after /admin.

   Customization

Add/edit HTML landing pages in /landings folder (volume-mounted in Docker)
Admin → "Upload Landing" to add new ones via bot
Prices edited via "Edit Prices" in admin panel
Add more languages in app/translations.py

Contributing
This project was born from a real need and built collaboratively with the help of several LLMs under human direction.

Concept & Core Strategy: Ab (Горилла in Chief 🦍)
Grok (xAI): In-depth code reviews, bug hunting & fixes (negotiation symmetry, final_time logic, flow consistency), UI/UX suggestions, and collaborative polishing throughout development.
Gemini (Google): Generated the initial MVP architectural foundation, core Python handlers, and performed final system-wide code reviews for version 0.8.
Claude (Anthropic): Gap analysis, feature implementation, and critical UX fixes for v0.8.

Pull requests welcome! Especially: new languages, cancellation flow, separate contacts collection, richer admin stats.
POSTGRES_PASSWORD=securepassword
POSTGRES_HOST=db
POSTGRES_PORT=5432
