# Voice AI Agent

## Project Overview

**Voice AI Agent** is an AI-powered voice assistant that enables users to interact with an intelligent agent through natural voice conversations. The project combines a React-based frontend with a Python backend to process user interactions and deliver real-time, conversational AI experiences.

## Backend Setup

### Step 1: Open Terminal in the Project Root

Navigate to the project directory:

```bash
cd web_voice_copilot
```

### Step 2: Initialize an Isolated Virtual Environment

**Windows:**

```bash
python -m venv backend\venv
```

**macOS / Linux:**

```bash
python3 -m venv backend/venv
```

### Step 3: Activate the Virtual Environment

**Windows (Git Bash):**

```bash
source backend/venv/Scripts/activate
```

**macOS / Linux:**

```bash
source backend/venv/bin/activate
```

### Step 4: Install Backend Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### Step 5: Start the Backend

Run the backend server:

```bash
python run.py
```

## Frontend Setup

### Step 6: Install Frontend Dependencies

From the project root, install the required Node.js packages:

```bash
npm install
```

### Step 7: Start the Frontend

Start the development server:

```bash
npm run dev
```

The frontend will then be available at the local development URL displayed in the terminal.
