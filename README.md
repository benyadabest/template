# FastAPI Supabase Phone Auth

A FastAPI application that implements phone authentication using Supabase and Twilio Verify.

## Features

* Phone number authentication using Twilio Verify
* Supabase integration for user management and data storage
* Session-based authentication
* Simple and clean UI with HTML/CSS
* Easy to extend

## Prerequisites

* Python 3.9+
* Supabase account and project
* Twilio account with Verify service

## Project Structure

```
.
├── main.py             # FastAPI application
├── static/             # Static files (CSS, JS)
├── templates/          # HTML templates
├── .env                # Environment variables (not in repo)
├── .env.example        # Example environment variables
└── requirements.txt    # Python dependencies
```

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/benyadabest/template.git
   cd template
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file:
   ```bash
   cp .env.example .env
   ```

4. Update the `.env` file with your credentials:
   * Add your Supabase project URL and service role key
   * Add your Twilio credentials (Account SID, Auth Token, Verify Service SID)
   * Generate a secret key for session management

5. Create the required table in Supabase:

```sql
-- Create profiles table
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ
);

-- Enable Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Allow users to view their own profile
CREATE POLICY "Users can view their own profile" 
  ON profiles FOR SELECT 
  USING (auth.uid() = id);

-- Allow service role to create profiles
CREATE POLICY "Service role can create profiles" 
  ON profiles FOR INSERT 
  TO service_role 
  WITH CHECK (true);
```

## Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```

2. Visit `http://localhost:8000` in your browser

## Features

* **Sign Up**: Create a new account with name and phone verification
* **Sign In**: Authenticate using phone number and OTP
* **Sign Out**: End the current session
* **Home Page**: Personalized greeting for authenticated users

## Development Notes

* For development/testing, you can set `DEBUG_BYPASS_OTP = True` in main.py to skip OTP verification
* Remember to set this back to `False` before deploying to production!

## License

MIT 