# Campus Lost & Found System

A web application for reporting and finding lost items on campus.

## Features

- 📸 **Upload Photos** - Upload images of lost/found items
- 🔍 **AI Image Matching** - Automatic similarity detection using perceptual hashing
- 📍 **Location Tagging** - Tag items with campus location
- 🔔 **Notifications** - Get alerts when similar items are found
- 👤 **Simple Login** - Use any temporary email (no verification)

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Image Processing**: Pillow, imagehash
- **Frontend**: HTML, CSS, JavaScript

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## Usage

1. Open browser to `http://localhost:5000`
2. Register with any email (temp mail works!)
3. Login and report lost/found items
4. The AI will automatically find similar items

## Project Structure

```
lost_found_campus/
├── app.py              # Main Flask application
├── templates/          # HTML templates
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── report.html
│   ├── search.html
│   └── item_detail.html
└── static/
    └── uploads/        # Image uploads
```

## AI Image Matching

Uses perceptual hashing (pHash) to find visually similar images:
- Generates a unique hash for each uploaded image
- Compares hashes to find matches
- Shows similarity percentage

## Demo Credentials

Use any temporary email service like:
- temp-mail.org
- 10minutemail.com
- guerrillamail.com
