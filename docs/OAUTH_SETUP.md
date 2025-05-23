# OAuth Setup Guide for AunooAI

This guide will help you set up OAuth authentication for the AunooAI application using Google, GitHub, and/or Microsoft as authentication providers.

## Overview

The OAuth implementation provides:
- Secure login via Google, GitHub, or Microsoft accounts
- Automatic user account creation and management
- Session management compatible with existing authentication
- Fallback to traditional username/password authentication

## Prerequisites

1. **Environment Setup**: Ensure your application environment is properly configured
2. **HTTPS (Production)**: OAuth providers require HTTPS in production
3. **Domain/Callback URLs**: You'll need to configure callback URLs with each provider

## Step 1: Install Dependencies

The required dependencies should already be added to `requirements.txt`. Install them:

```bash
pip install -r requirements.txt
```

Key OAuth dependencies:
- `authlib>=1.2.0` - OAuth client library
- `httpx>=0.24.0` - HTTP client for API calls

## Step 2: Configure OAuth Providers

### Google OAuth Setup

1. **Google Cloud Console**:
   - Go to [Google Cloud Console](https://console.developers.google.com/)
   - Create a new project or select an existing one
   - Enable the **Google+ API** (or newer Google Identity API)

2. **Create OAuth Credentials**:
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Application type: "Web application"
   - Name: "AunooAI OAuth"

3. **Configure Redirect URIs**:
   - For development: `http://localhost:8000/auth/callback/google`
   - For production: `https://yourdomain.com/auth/callback/google`

4. **Get Credentials**:
   - Copy the **Client ID** and **Client Secret**

### GitHub OAuth Setup

1. **GitHub Settings**:
   - Go to [GitHub Developer Settings](https://github.com/settings/applications/new)
   - Click "New OAuth App"

2. **Application Details**:
   - Application name: "AunooAI"
   - Homepage URL: `http://localhost:8000` (or your domain)
   - Application description: "AunooAI OAuth Authentication"
   - Authorization callback URL: `http://localhost:8000/auth/callback/github`

3. **Get Credentials**:
   - Copy the **Client ID** and **Client Secret**

### Microsoft OAuth Setup (Optional)

1. **Azure Portal**:
   - Go to [Azure Portal](https://portal.azure.com/)
   - Navigate to "Azure Active Directory" > "App registrations"
   - Click "New registration"

2. **Application Details**:
   - Name: "AunooAI"
   - Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
   - Redirect URI: `http://localhost:8000/auth/callback/microsoft`

3. **Get Credentials**:
   - Copy the **Application (client) ID**
   - In "Certificates & secrets", create a new client secret

## Step 3: Environment Configuration

1. **Copy Environment Template**:
   ```bash
   cp .env.oauth.example .env.oauth
   ```

2. **Edit Environment Variables**:
   Add your OAuth credentials to your `.env` file:

   ```env
   # Google OAuth
   GOOGLE_CLIENT_ID=your_google_client_id_here
   GOOGLE_CLIENT_SECRET=your_google_client_secret_here

   # GitHub OAuth  
   GITHUB_CLIENT_ID=your_github_client_id_here
   GITHUB_CLIENT_SECRET=your_github_client_secret_here

   # Microsoft OAuth (optional)
   MICROSOFT_CLIENT_ID=your_microsoft_client_id_here
   MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret_here

   # OAuth Settings
   OAUTH_REDIRECT_AFTER_LOGIN=/dashboard
   OAUTH_ALLOW_NEW_USER_REGISTRATION=true
   ```

## Step 4: Database Migration

Run the OAuth database migration to create the required tables:

```bash
# If you have a migration script
python run_migration.py app/database/migrations/add_oauth_tables.sql

# Or manually run the SQL in your database client
sqlite3 app/data/fnaapp.db < app/database/migrations/add_oauth_tables.sql
```

This creates:
- `oauth_users` table for OAuth user data
- `oauth_sessions` table for session tracking
- Appropriate indexes for performance

## Step 5: Test the Implementation

1. **Start the Application**:
   ```bash
   python app/main.py
   # or
   uvicorn app.main:app --reload
   ```

2. **Access Login Page**:
   - Go to `http://localhost:8000/login`
   - You should see OAuth provider buttons (Google, GitHub, etc.)

3. **Test OAuth Flow**:
   - Click on a provider button (e.g., "Continue with Google")
   - You'll be redirected to the provider's login page
   - After successful authentication, you'll be redirected back to the app
   - Check that you're logged in and redirected to the dashboard

4. **Verify Database**:
   ```bash
   sqlite3 app/data/fnaapp.db
   .tables  # Should show oauth_users and oauth_sessions
   SELECT * FROM oauth_users;  # Should show your OAuth user
   ```

## Step 6: Production Deployment

### HTTPS Configuration

OAuth providers require HTTPS in production. Ensure your deployment:
1. Uses SSL certificates
2. Updates callback URLs to use `https://`
3. Sets proper CORS settings

### Environment Variables for Production

```env
# Production OAuth Settings
OAUTH_REQUIRE_EMAIL_VERIFICATION=true
OAUTH_ALLOW_NEW_USER_REGISTRATION=false  # Set to false for private apps
OAUTH_DEBUG_MODE=false
```

### Update Provider Callback URLs

Update all OAuth applications with production URLs:
- Google: `https://yourdomain.com/auth/callback/google`
- GitHub: `https://yourdomain.com/auth/callback/github`  
- Microsoft: `https://yourdomain.com/auth/callback/microsoft`

## Troubleshooting

### Common Issues

1. **"OAuth provider not configured"**:
   - Check that environment variables are set correctly
   - Verify the provider is listed in `/auth/providers` endpoint

2. **"OAuth login failed: Client error '404 Not Found'" or "Missing jwks_uri in metadata"**:
   - These were issues with Google's OpenID discovery URL that have been fixed
   - The implementation now uses the correct OIDC discovery URL: `https://accounts.google.com/.well-known/openid-configuration`
   - Restart your application to pick up the fix

3. **"device_id and device_name are required for private IP" (Error 400: invalid_request)**:
   - Google OAuth requires special configuration when using private IP addresses (192.168.x.x, 10.x.x.x, etc.)
   - **Solution 1 (Recommended)**: Use `localhost` instead of private IP in your redirect URI
     - Configure Google OAuth with: `http://localhost:8000/auth/callback/google`
     - Access your app via: `http://localhost:8000`
   - **Solution 2**: Configure device credentials (for private IP access)
     - Set `GOOGLE_DEVICE_ID=your_unique_device_id` in your .env file
     - Set `GOOGLE_DEVICE_NAME=AunooAI` in your .env file
   - **Solution 3**: Use public domain with port forwarding or reverse proxy

4. **"OAuth client was not found" (Error 401: invalid_client)**:
   - This means Google doesn't recognize your client credentials
   - **Check your credentials**:
     - Verify `GOOGLE_CLIENT_ID` is correct (should be a long string ending in `.apps.googleusercontent.com`)
     - Verify `GOOGLE_CLIENT_SECRET` is correct (should be a shorter alphanumeric string)
     - Ensure there are no extra spaces or quotes in your environment variables
   - **Verify in Google Console**:
     - Go to [Google Cloud Console](https://console.developers.google.com/)
     - Navigate to "APIs & Services" > "Credentials"
     - Confirm your OAuth 2.0 Client ID exists and is enabled
     - Check that the client ID matches exactly what you have in your `.env` file
   - **Check API enablement**: Ensure Google+ API or Google Identity API is enabled

5. **"Authentication failed"**:
   - Check callback URLs match exactly
   - Verify client credentials are correct
   - Check application logs for detailed error messages

6. **"Session not found"**:
   - Ensure SessionMiddleware is configured in FastAPI
   - Check that session cookies are being set

7. **Provider-specific errors**:
   - **Google**: Ensure Google+ API is enabled
   - **GitHub**: Check that email permission is granted
   - **Microsoft**: Verify tenant settings allow external logins

### Debug Mode

Enable OAuth debug mode for detailed logging:

```env
OAUTH_DEBUG_MODE=true
```

This will log additional information about the OAuth flow.

### Testing Endpoints

Test OAuth functionality with these endpoints:

```bash
# Check configured providers
curl http://localhost:8000/auth/providers

# Check authentication status  
curl http://localhost:8000/auth/status

# Check OAuth configuration (helpful for debugging)
curl http://localhost:8000/auth/config-check

# Manual logout (POST request)
curl -X POST http://localhost:8000/auth/logout
```

The `/auth/config-check` endpoint is particularly useful for debugging credential issues. It will show:
- Which environment variables are set (without exposing the actual values)
- The length of your credentials (to help verify they're complete)
- A preview of your client ID (first 8 characters)
- Whether device credentials are configured

## Security Considerations

1. **Secret Management**: Never commit OAuth secrets to version control
2. **HTTPS Only**: Always use HTTPS in production
3. **Session Security**: Use strong session secrets
4. **Email Verification**: Consider enabling email verification in production
5. **User Registration**: Consider disabling new user registration for private applications

## Integration with Existing Authentication

The OAuth implementation works alongside existing username/password authentication:

- OAuth users and traditional users can coexist
- Session verification works for both authentication methods  
- The login page shows both OAuth and traditional login options
- All existing protected routes work with OAuth users

## API Reference

### OAuth Endpoints

- `GET /auth/providers` - List configured OAuth providers
- `GET /auth/login/{provider}` - Initiate OAuth login
- `GET /auth/callback/{provider}` - OAuth callback handler
- `POST /auth/logout` - Logout user
- `GET /auth/status` - Get authentication status

### Configuration

OAuth configuration is managed through:
- `app.config.oauth_config.py` - Provider configurations
- `app.security.oauth.py` - OAuth service implementation
- `app.security.oauth_users.py` - User management utilities

## Support

For issues or questions:
1. Check the application logs
2. Verify provider configurations
3. Test with OAuth debug mode enabled
4. Consult provider-specific documentation