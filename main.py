import os
from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import requests
from supabase import create_client, Client

# Load configuration from environment variables
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")  # For session middleware

# Initialize FastAPI app
app = FastAPI()

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Mount static files (if you add CSS or images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates (templates folder)
templates = Jinja2Templates(directory="templates")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ---------- Twilio Verify Helper Functions ----------

def send_otp(phone_number: str):
    """Send OTP using Twilio Verify."""
    url = f"https://verify.twilio.com/v2/Services/{TWILIO_VERIFY_SERVICE_SID}/Verifications"
    data = {
        'To': phone_number,
        'Channel': 'sms'
    }
    response = requests.post(url, data=data, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    return response.json()

def verify_otp(phone_number: str, code: str):
    """Verify OTP code using Twilio Verify."""
    url = f"https://verify.twilio.com/v2/Services/{TWILIO_VERIFY_SERVICE_SID}/VerificationCheck"
    data = {
        'To': phone_number,
        'Code': code
    }
    response = requests.post(url, data=data, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    return response.json()

# ---------- Routes ----------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Home page: if signed in, greet the user by name; otherwise show a welcome message.
    """
    user = request.session.get("user")
    return templates.TemplateResponse("home.html", {"request": request, "user": user})

@app.get("/signup", response_class=HTMLResponse)
async def get_signup(request: Request):
    """Display the signup form for name and phone number."""
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def post_signup(request: Request, name: str = Form(...), phone: str = Form(...)):
    """
    Process the signup form:
      - Save pending user info (name and phone) in session.
      - Trigger sending OTP via Twilio.
      - Redirect to /verify for OTP input.
    """
    # Save pending user info in session
    request.session["pending_user"] = {"name": name, "phone": phone}
    # Send OTP via Twilio
    otp_response = send_otp(phone)
    if otp_response.get("status") not in ["pending", "approved"]:
        raise HTTPException(status_code=500, detail="Failed to send OTP")
    return RedirectResponse(url="/verify", status_code=status.HTTP_302_FOUND)

@app.get("/verify", response_class=HTMLResponse)
async def get_verify(request: Request):
    """Display the OTP verification form."""
    pending = request.session.get("pending_user")
    if not pending:
        return RedirectResponse(url="/signup")
    return templates.TemplateResponse("verify.html", {"request": request, "phone": pending["phone"]})

@app.post("/verify")
async def post_verify(request: Request, otp: str = Form(...)):
    """
    Process OTP verification:
      - Retrieve pending user info from session.
      - Verify OTP with Twilio.
      - If successful, create the user in Supabase auth.
      - Create a user profile in the database.
      - Save the user info in session and redirect to home.
    """
    pending = request.session.get("pending_user")
    if not pending:
        raise HTTPException(status_code=400, detail="No pending user found. Please sign up first.")

    phone = pending["phone"]
    name = pending["name"]

    verify_result = verify_otp(phone, otp)
    if verify_result.get("status") != "approved":
        # Optionally: Log the actual Twilio error `verify_result` for debugging
        raise HTTPException(status_code=400, detail="OTP verification failed. Please try again.")

    try:
        # Step 1: Create the user in Supabase Auth
        auth_response = supabase.auth.admin.create_user({
            "phone": phone,
            "phone_confirm": True,
            "user_metadata": {"name": name}
        })
        
        # Check if user creation was successful
        if not auth_response or not auth_response.user:
             raise Exception("Supabase user creation response was invalid.")
        
        created_user = auth_response.user
        user_id = created_user.id
        
        # Step 2: Create a profile record in the profiles table
        profile_data = {
            "id": user_id,  # Use the same ID as the auth user
            "name": name,
            "phone": phone,
            "created_at": "now()"  # Supabase SQL function for current timestamp
        }
        
        # Insert the profile data
        profile_response = supabase.table("profiles").insert(profile_data).execute()
        
        # Check for errors in the profile creation
        if hasattr(profile_response, 'error') and profile_response.error:
            print(f"Profile creation error: {profile_response.error}")
            # Optionally: Roll back auth user creation if profile creation fails
            # supabase.auth.admin.delete_user(user_id)
            raise Exception(f"Failed to create user profile: {profile_response.error}")

    except Exception as e:
        # Log the specific error for better debugging
        print(f"Supabase Error: {e}")
        raise HTTPException(status_code=500, detail="Error creating user in Supabase: " + str(e))

    # Get user info to store in session
    user_for_session = {
        "id": user_id,
        "name": name,
        "phone": phone
    }

    # Save the signed-in user in session and clear pending info
    request.session["user"] = user_for_session
    request.session.pop("pending_user", None)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@app.get("/signout")
async def signout(request: Request):
    """Clear the session to sign the user out."""
    request.session.pop("user", None)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

@app.get("/signin", response_class=HTMLResponse)
async def get_signin(request: Request):
    """Display the sign-in form for phone number input."""
    return templates.TemplateResponse("signin.html", {"request": request})

@app.post("/signin")
async def post_signin(request: Request, phone: str = Form(...)):
    """
    Process the sign-in form:
      - Check if the phone exists in Supabase
      - Send OTP via Twilio
      - Redirect to /signin/verify for OTP verification
    """
    try:
        # Store the phone in session for verification step
        request.session["signin_phone"] = phone
        
        # Send OTP via Twilio
        otp_response = send_otp(phone)
        if otp_response.get("status") not in ["pending", "approved"]:
            raise HTTPException(status_code=500, detail="Failed to send OTP")
        
        return RedirectResponse(url="/signin/verify", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"Error in signin: {e}")
        raise HTTPException(status_code=500, detail="Error during sign-in")

@app.get("/signin/verify", response_class=HTMLResponse)
async def get_signin_verify(request: Request):
    """Display the OTP verification form for sign-in."""
    phone = request.session.get("signin_phone")
    if not phone:
        return RedirectResponse(url="/signin")
    return templates.TemplateResponse("signin_verify.html", {"request": request, "phone": phone})

@app.post("/signin/verify")
async def post_signin_verify(request: Request, otp: str = Form(...)):
    """
    Process OTP verification for sign-in:
      - Verify OTP with Twilio
      - If successful, retrieve user from Supabase
      - Save user info in session and redirect to home
    """
    phone = request.session.get("signin_phone")
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number found. Please sign in first.")
    
    verify_result = verify_otp(phone, otp)
    if verify_result.get("status") != "approved":
        raise HTTPException(status_code=400, detail="OTP verification failed. Please try again.")
    
    try:
        # Fetch user profile from database using the phone number
        print(f"Searching for profile with phone: {phone}")
        profile_response = supabase.table("profiles").select("*").eq("phone", phone).execute()
        
        # Log the raw response for debugging
        print(f"Supabase response: {profile_response}")
        print(f"Response data: {getattr(profile_response, 'data', 'No data attribute')}")
        
        # Check if we found a user
        if not hasattr(profile_response, 'data') or not profile_response.data:
            print(f"No profile data found for phone: {phone}")
            raise HTTPException(status_code=404, detail="No user found with this phone number")
        
        if len(profile_response.data) == 0:
            print(f"Empty profile data array for phone: {phone}")
            raise HTTPException(status_code=404, detail="No user found with this phone number")
        
        # Get the first matching user (should be only one)
        user_profile = profile_response.data[0]
        print(f"Found user profile: {user_profile}")
        
        # Create session with user info
        user_for_session = {
            "id": user_profile.get("id"),
            "name": user_profile.get("name"),
            "phone": user_profile.get("phone")
        }
        
        print(f"Created session data: {user_for_session}")
        
        # Save the signed-in user in session and clear signin phone
        request.session["user"] = user_for_session
        request.session.pop("signin_phone", None)
        
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    except HTTPException as he:
        # Re-raise HTTP exceptions with the same status and detail
        raise he
    except Exception as e:
        print(f"Error in signin verification: {e}")
        raise HTTPException(status_code=500, detail="Error during sign-in verification")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True)
