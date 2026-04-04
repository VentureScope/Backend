# CORS Configuration Guide

## Overview

The VentureScope backend implements industry-standard CORS (Cross-Origin Resource Sharing) configuration that is **development-friendly** and **production-secure**:

- **Development**: Allows all origins (`*`) by default for easy frontend integration
- **Production**: Restricts to specific domains only for security

## Quick Setup

### For Development (Easiest)

Create a `.env` file with:

```bash
ENVIRONMENT=development
CORS_ORIGINS=*
```

This allows **any origin** to make requests to your API - perfect for development!

### For Production

```bash
ENVIRONMENT=production
CORS_ORIGINS=["https://yourapp.com","https://www.yourapp.com"]
FRONTEND_URL=https://yourapp.com
```

## Configuration Options

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment type | `development`, `production` |
| `CORS_ORIGINS` | Allowed origins | `*`, `http://localhost:3000`, JSON array |
| `FRONTEND_URL` | Primary frontend URL | `http://localhost:3000` |

### CORS_ORIGINS Format Options

You can specify `CORS_ORIGINS` in multiple formats:

#### 1. Wildcard (Recommended for Development)
```bash
CORS_ORIGINS=*
```
Allows **all origins** - easiest for development.

#### 2. Comma-Separated String
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080
```

#### 3. JSON Array
```bash
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:8080"]
```

#### 4. Single Origin
```bash
CORS_ORIGINS=http://localhost:3000
```

## Environment-Specific Behavior

### Development Mode (`ENVIRONMENT=development`)

- **`CORS_ORIGINS=*`**: ✅ Allows ALL origins (recommended)
- **`CORS_ORIGINS=specific`**: ✅ Uses only those specific origins
- **No localhost restrictions**: ✅ All localhost ports allowed

```bash
# Most permissive - allows any frontend
ENVIRONMENT=development
CORS_ORIGINS=*
```

### Production Mode (`ENVIRONMENT=production`)

- **`CORS_ORIGINS=*`**: 🔒 Automatically falls back to `FRONTEND_URL` (secure)
- **`CORS_ORIGINS=specific`**: 🔒 Uses only those origins
- **Localhost filtering**: 🔒 Automatically removes localhost origins for security

```bash
# Secure production setup
ENVIRONMENT=production
CORS_ORIGINS=["https://myapp.com","https://www.myapp.com"]
FRONTEND_URL=https://myapp.com
```

## Frontend Integration

### JavaScript Fetch

```javascript
// Works with CORS_ORIGINS=* in development
fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer your-jwt-token'
  },
  credentials: 'include',  // Important for CORS with credentials
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'password'
  })
})
```

### Axios Configuration

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  withCredentials: true,  // Enable CORS credentials
  headers: {
    'Content-Type': 'application/json',
  }
});

// Add auth token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### React Hook Example

```javascript
import { useState, useEffect } from 'react';

function useApi(url, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api${url}`, {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...options.headers
          },
          ...options
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [url]);

  return { data, loading, error };
}
```

## Troubleshooting

### Common CORS Errors

#### Error: "Access to fetch at ... has been blocked by CORS policy"

**Quick Fix:**
```bash
# Add to your .env file
ENVIRONMENT=development
CORS_ORIGINS=*
```

**Other Solutions:**
1. Check your `.env` file exists and has correct values
2. Restart your backend after changing `.env`
3. Verify `ENVIRONMENT=development` for local dev

#### Error: "Credentials include but Allow-Credentials not set"

**Solution:** The backend automatically sets `allow_credentials=True`. Ensure your frontend uses:
- `credentials: 'include'` in fetch requests
- `withCredentials: true` in axios

### Testing CORS

#### Quick Browser Test
Open your browser console on any page and run:
```javascript
fetch('http://localhost:8000/api/health', {
  method: 'GET',
  credentials: 'include'
}).then(r => r.json()).then(console.log)
```

#### Command Line Test
```bash
# Test preflight request
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type,Authorization" \
     -X OPTIONS \
     http://localhost:8000/api/auth/login \
     -v
```

Expected response headers:
```
access-control-allow-origin: *  (or your specific origin)
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

## Common Development Setups

### React / Next.js (Port 3000)
```bash
ENVIRONMENT=development
CORS_ORIGINS=*
```

### Vite (Port 5173)
```bash
ENVIRONMENT=development
CORS_ORIGINS=*
```

### Vue CLI (Port 8080)
```bash
ENVIRONMENT=development  
CORS_ORIGINS=*
```

### Multiple Frontend Apps
```bash
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080
```

## Production Deployment

### Security Checklist
- [ ] Set `ENVIRONMENT=production`
- [ ] Specify exact domains in `CORS_ORIGINS`
- [ ] Use HTTPS URLs only
- [ ] Set `FRONTEND_URL` as fallback
- [ ] Test CORS in production environment

### Production Examples

#### Single Domain
```bash
ENVIRONMENT=production
CORS_ORIGINS=["https://myapp.com"]
FRONTEND_URL=https://myapp.com
```

#### Multiple Domains
```bash
ENVIRONMENT=production
CORS_ORIGINS=["https://myapp.com","https://www.myapp.com","https://app.myapp.com"]
FRONTEND_URL=https://myapp.com
```

#### With CDN/Subdomains
```bash
ENVIRONMENT=production
CORS_ORIGINS=["https://myapp.com","https://cdn.myapp.com","https://api.myapp.com"]
FRONTEND_URL=https://myapp.com
```

## Environment Variable Loading

The configuration uses Pydantic Settings which loads environment variables in this order:

1. Environment variables
2. `.env` file in the project root
3. Default values in the code

### Validation

The system automatically:
- ✅ Validates origin URLs
- ✅ Parses different formats (wildcard, comma-separated, JSON)
- ✅ Filters localhost origins in production
- ✅ Provides secure defaults

### Debugging

Check the backend logs on startup for CORS configuration:
```
INFO: CORS Configuration:
INFO:   Environment: development
INFO:   Origins: *
INFO:   Allow Credentials: True
```

## Advanced Configuration

### Custom Headers
The backend automatically allows these headers:
- `Accept`, `Accept-Encoding`, `Authorization`
- `Content-Type`, `DNT`, `Origin`, `User-Agent`  
- `X-CSRFToken`, `X-Requested-With`

### Custom Methods
All standard HTTP methods are allowed:
- `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, `HEAD`

### Exposed Headers
These headers are automatically exposed to frontend JavaScript for programmatic access:

- **`Content-Length`**: Size of response body in bytes
- **`Content-Range`**: Range information for partial content requests  
- **`Content-Type`**: MIME type of the response content
- **`Date`**: Date and time when the response was generated
- **`Server`**: Web server software information
- **`Transfer-Encoding`**: Transfer encoding method used

**Why these headers?** 
- They're commonly needed by frontend applications for progress tracking, content handling, and debugging
- They're safe to expose (no sensitive information)
- Required for proper HTTP client functionality

**Customization**: These are configured in `app/main.py` in the `expose_headers` parameter of the CORS middleware. You can modify this list if your frontend needs access to additional response headers.

## Summary

- **Development**: Use `CORS_ORIGINS=*` for maximum flexibility
- **Production**: Use specific domains for security
- **Environment variables**: Loaded from `.env` file automatically
- **Flexible formats**: Support for wildcard, comma-separated, and JSON array origins
- **Auto-security**: Localhost origins filtered in production automatically