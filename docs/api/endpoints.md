# API Documentation

## Overview
VentureScope Backend provides a RESTful API for user authentication, user management, and career guidance features.

## Base URL
- **Development**: `http://localhost:8000`
- **Production**: TBD

## Authentication
The API uses JWT (JSON Web Token) bearer authentication for protected endpoints.

### Token Usage
```
Authorization: Bearer <your-jwt-token>
```

## Endpoints

### Health Check
- **GET** `/api/health`
- **Description**: Check API health status
- **Authentication**: None required
- **Response**: `{"status": "ok"}`

### Authentication

#### Register User
- **POST** `/api/auth/register`
- **Description**: Create new user account
- **Authentication**: None required
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword123",
    "full_name": "John Doe",
    "career_interest": "Software Engineering",
    "role": "professional"
  }
  ```
- **Response**:
  ```json
  {
    "id": "uuid",
    "email": "user@example.com", 
    "full_name": "John Doe",
    "github_username": null,
    "career_interest": "Software Engineering",
    "role": "professional",
    "is_active": true,
    "is_admin": false
  }
  ```

#### Login
- **POST** `/api/auth/login`
- **Description**: Authenticate user and get access token
- **Authentication**: None required
- **Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword"
  }
  ```
- **Response**:
  ```json
  {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer"
  }
  ```

#### Logout
- **POST** `/api/auth/logout`
- **Description**: Logout user by invalidating the current access token
- **Authentication**: Required (Bearer token)
- **Response**:
  ```json
  {
    "message": "Successfully logged out"
  }
  ```
- **Error Responses**:
  - **401**: Invalid or expired token
  - **400**: Token already invalidated (double logout attempt)

#### OAuth Login (Google)
- **GET** `/api/auth/oauth/google/login`
- **Description**: Initiate Google OAuth flow and receive authorization URL
- **Authentication**: None required
- **Response**:
  ```json
  {
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "state": "secure-state-token"
  }
  ```

#### OAuth Callback (Google)
- **POST** `/api/auth/oauth/google/callback`
- **Description**: Exchange Google authorization code for app access token
- **Authentication**: None required
- **Body**:
  ```json
  {
    "code": "google-auth-code",
    "state": "secure-state-token"
  }
  ```
- **Response**:
  ```json
  {
    "access_token": "app-jwt-token",
    "token_type": "bearer",
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "full_name": "John Doe",
      "github_username": null,
      "career_interest": null,
      "role": "professional",
      "is_active": true,
      "is_admin": false
    }
  }
  ```

#### OAuth Login (GitHub)
- **GET** `/api/auth/oauth/github/login`
- **Description**: Initiate GitHub OAuth flow and receive authorization URL
- **Authentication**: None required
- **Response**:
  ```json
  {
    "authorization_url": "https://github.com/login/oauth/authorize?...",
    "state": "secure-state-token"
  }
  ```

#### OAuth Callback (GitHub)
- **POST** `/api/auth/oauth/github/callback`
- **Description**: Exchange GitHub authorization code for app access token
- **Authentication**: None required
- **Body**:
  ```json
  {
    "code": "github-auth-code",
    "state": "secure-state-token"
  }
  ```
- **Response**: Same as Google OAuth callback response format

### User Management (Self-Service)

#### Get Current User
- **GET** `/api/users/me`
- **Description**: Get current authenticated user information
- **Authentication**: Required (Bearer token)
- **Response**:
  ```json
  {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "github_username": null,
    "career_interest": "Software Engineering", 
    "role": "professional",
    "is_active": true,
    "is_admin": false
  }
  ```

#### Update Profile
- **PATCH** `/api/users/me`
- **Description**: Update current user's profile
- **Authentication**: Required (Bearer token)
- **Body** (all fields optional):
  ```json
  {
    "full_name": "Jane Doe",
    "github_username": "janedoe",
    "career_interest": "Data Science"
  }
  ```
- **Response**: Updated user object

#### Change Password
- **PUT** `/api/users/me/password`
- **Description**: Change current user's password
- **Authentication**: Required (Bearer token)
- **Body**:
  ```json
  {
    "current_password": "oldpassword123",
    "new_password": "newpassword456"
  }
  ```
- **Response**:
  ```json
  {
    "message": "Password changed successfully",
    "detail": "Please use your new password for future logins"
  }
  ```

#### Delete Account
- **DELETE** `/api/users/me`
- **Description**: Delete current user's account (soft delete - deactivates account)
- **Authentication**: Required (Bearer token)
- **Body**:
  ```json
  {
    "password": "yourpassword"
  }
  ```
- **Response**:
  ```json
  {
    "message": "Account deleted successfully",
    "detail": "Your account has been deactivated. Contact support to restore."
  }
  ```

### Admin Endpoints

> **Note**: All admin endpoints require admin privileges (`is_admin: true`).

#### List All Users
- **GET** `/api/admin/users`
- **Description**: List all users with pagination
- **Authentication**: Required (Admin only)
- **Query Parameters**:
  - `page` (int, default: 1): Page number
  - `per_page` (int, default: 10, max: 100): Items per page
  - `include_inactive` (bool, default: false): Include deactivated users
- **Response**:
  ```json
  {
    "items": [
      {
        "id": "uuid",
        "email": "user@example.com",
        "full_name": "John Doe",
        "role": "professional",
        "is_active": true,
        "is_admin": false
      }
    ],
    "total": 100,
    "page": 1,
    "per_page": 10,
    "pages": 10
  }
  ```

#### Get User by ID
- **GET** `/api/admin/users/{user_id}`
- **Description**: Get any user by ID
- **Authentication**: Required (Admin only)
- **Response**: User object

#### Update User
- **PATCH** `/api/admin/users/{user_id}`
- **Description**: Update any user's information
- **Authentication**: Required (Admin only)
- **Body** (all fields optional):
  ```json
  {
    "full_name": "Updated Name",
    "github_username": "newusername",
    "career_interest": "Machine Learning",
    "role": "student",
    "is_active": true,
    "is_admin": false
  }
  ```
- **Response**: Updated user object

#### Delete User
- **DELETE** `/api/admin/users/{user_id}`
- **Description**: Delete a user (soft delete by default)
- **Authentication**: Required (Admin only)
- **Query Parameters**:
  - `hard_delete` (bool, default: false): Permanently delete user
- **Response**:
  ```json
  {
    "message": "User deactivated",
    "detail": "User account has been deactivated"
  }
  ```

#### Reactivate User
- **POST** `/api/admin/users/{user_id}/reactivate`
- **Description**: Reactivate a deactivated user
- **Authentication**: Required (Admin only)
- **Response**: Reactivated user object

## Error Responses

### Standard Error Format
```json
{
  "detail": "Error message description"
}
```

### HTTP Status Codes
- **200**: Success
- **400**: Bad Request - Invalid input data
- **401**: Unauthorized - Missing or invalid token
- **403**: Forbidden - Insufficient permissions (e.g., non-admin accessing admin endpoints)
- **404**: Not Found - Resource doesn't exist
- **422**: Validation Error - Request body validation failed
- **500**: Internal Server Error

### Validation Errors
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Interactive Documentation
- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`

## Rate Limiting
Currently no rate limiting implemented. Consider implementing for production.

## Versioning
API is currently unversioned. Future versions should follow semantic versioning.

## Last Updated
April 3, 2026 - Added Logout Endpoint with Token Invalidation (Token Blocklist)