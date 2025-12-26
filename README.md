# Psychotherapy Booking Bot

Telegram bot for psychotherapists to manage client bookings: online/onsite, individual/couple sessions, time negotiation, waitlist, and admin tools. Supports Russian and Armenian out of the box.

Version: **0.8** (pre-release, stable and usable)

Perfect for solo practitioners who want a simple, professional booking flow directly in Telegram without third-party calendars.

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
